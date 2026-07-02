"use client";

import { useState, useRef, type KeyboardEvent, type ChangeEvent } from "react";
import { Send, ImagePlus, X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatInputProps {
  onSend: (message: string, imageBase64: string | null) => void;
  disabled?: boolean;
}

const MAX_BYTES = 10 * 1024 * 1024;

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [input, setInput] = useState("");
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = () => {
    const trimmed = input.trim();
    if ((!trimmed && !imageBase64) || disabled) return;
    onSend(trimmed, imageBase64);
    setInput("");
    setImageBase64(null);
    setImagePreview(null);
    setImageError(null);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setImageError("图片不能超过 10MB");
      e.target.value = "";
      return;
    }
    if (!file.type.startsWith("image/")) {
      setImageError("请选择图片文件");
      e.target.value = "";
      return;
    }
    setImageError(null);
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      const base64 = dataUrl.split(",")[1] ?? null;
      setImagePreview(dataUrl);
      setImageBase64(base64);
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const clearImage = () => {
    setImageBase64(null);
    setImagePreview(null);
    setImageError(null);
  };

  return (
    <div className="border-t border-border bg-background px-4 py-3 shrink-0">
      <div className="max-w-3xl mx-auto flex flex-col gap-2">
        {imagePreview && (
          <div className="relative inline-block w-fit">
            <img
              src={imagePreview}
              alt="upload preview"
              className="h-20 w-20 rounded-lg object-cover border border-input"
            />
            <button
              type="button"
              onClick={clearImage}
              className="absolute -top-2 -right-2 rounded-full bg-background border border-input p-0.5 hover:bg-muted"
              aria-label="移除图片"
            >
              <X size={14} />
            </button>
          </div>
        )}
        {imageError && (
          <div className="text-xs text-destructive">{imageError}</div>
        )}
        <div className="flex items-end gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="hidden"
          />
          <Button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            size="icon"
            variant="outline"
            className="h-10 w-10 rounded-xl shrink-0"
            aria-label="上传图片"
          >
            <ImagePlus size={16} />
          </Button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            placeholder="请输入您的医美问题..."
            disabled={disabled}
            rows={1}
            className="flex-1 resize-none rounded-xl border border-input bg-background px-4 py-3 text-sm
                       focus:outline-none focus:ring-2 focus:ring-ring/30 focus:border-ring
                       disabled:opacity-50 disabled:cursor-not-allowed
                       placeholder:text-muted-foreground"
          />
          <Button
            onClick={handleSend}
            disabled={disabled || (!input.trim() && !imageBase64)}
            size="icon"
            className="h-10 w-10 rounded-xl shrink-0"
          >
            <Send size={16} />
          </Button>
        </div>
      </div>
    </div>
  );
}
