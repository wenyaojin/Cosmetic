"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { ImagePlus, X, Play, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const MAX_BYTES = 10 * 1024 * 1024;

export interface UploadSubmitValue {
  imageBase64: string | null;
  age: number | null;
  gender: "female" | "male" | null;
  useFixture: boolean;
}

interface UploadZoneProps {
  onSubmit: (v: UploadSubmitValue) => void;
  loading: boolean;
}

export function UploadZone({ onSubmit, loading }: UploadZoneProps) {
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [age, setAge] = useState<string>("");
  const [gender, setGender] = useState<"" | "female" | "male">("");
  const [useFixture, setUseFixture] = useState<boolean>(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
      const b64 = dataUrl.split(",")[1] ?? null;
      setImagePreview(dataUrl);
      setImageBase64(b64);
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const clearImage = () => {
    setImageBase64(null);
    setImagePreview(null);
    setImageError(null);
  };

  const canSubmit = useFixture || !!imageBase64;

  const handleSubmit = () => {
    if (!canSubmit || loading) return;
    const parsedAge = age.trim() ? parseInt(age, 10) : null;
    onSubmit({
      imageBase64: useFixture ? null : imageBase64,
      age: Number.isFinite(parsedAge) ? parsedAge : null,
      gender: gender || null,
      useFixture,
    });
  };

  return (
    <div className="border border-border rounded-xl bg-card p-6 flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row gap-4 items-start">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          onChange={handleFileChange}
          className="hidden"
        />

        {imagePreview ? (
          <div className="relative">
            <img
              src={imagePreview}
              alt="upload preview"
              className="h-32 w-32 rounded-lg object-cover border border-input"
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
        ) : (
          <Button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading || useFixture}
            variant="outline"
            className="h-32 w-32 flex flex-col gap-1 rounded-lg"
          >
            <ImagePlus size={24} />
            <span className="text-xs">选择正面照</span>
          </Button>
        )}

        <div className="flex-1 grid grid-cols-2 sm:grid-cols-3 gap-3 w-full">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">年龄（选填）</label>
            <input
              type="number"
              min={1}
              max={120}
              value={age}
              onChange={(e) => setAge(e.target.value)}
              disabled={loading}
              placeholder="如 45"
              className="rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring/30"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">性别（选填）</label>
            <select
              value={gender}
              onChange={(e) => setGender(e.target.value as "" | "female" | "male")}
              disabled={loading}
              className="rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring/30"
            >
              <option value="">未选择</option>
              <option value="female">女</option>
              <option value="male">男</option>
            </select>
          </div>
          <label className="flex items-center gap-2 sm:col-span-1 col-span-2 mt-4 sm:mt-6 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={useFixture}
              onChange={(e) => setUseFixture(e.target.checked)}
              disabled={loading}
              className="h-4 w-4"
            />
            <span>使用预置样例</span>
          </label>
        </div>
      </div>

      {imageError && <div className="text-xs text-destructive">{imageError}</div>}

      <div className="flex items-center justify-between gap-3">
        <div className="text-xs text-muted-foreground">
          {useFixture
            ? "预置样例：patient_dff3abf1（45F）· 秒开，不消耗 API"
            : "真实生成：qwen-vl-max 诊断 + qwen-image-edit 生图，约 3-4 分钟"}
        </div>
        <Button onClick={handleSubmit} disabled={!canSubmit || loading} className="gap-2">
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          {loading ? "生成中…" : "生成术后模拟"}
        </Button>
      </div>
    </div>
  );
}
