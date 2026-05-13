"use client";

import { motion } from "framer-motion";
import { Bot, User, AlertTriangle, BookOpen, Copy, RefreshCw, ThumbsUp, ThumbsDown } from "lucide-react";
import { MarkdownRenderer } from "@/components/common/MarkdownRenderer";
import { LoadingDots } from "@/components/common/LoadingDots";
import { Button } from "@/components/ui/button";
import type { Message } from "@/types/chat";

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && (
        <div className="shrink-0 w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center mt-1">
          <Bot size={14} className="text-primary" />
        </div>
      )}

      <div className={`max-w-[80%] min-w-0 ${isUser ? "order-first" : ""}`}>
        {/* Risk flags */}
        {!isUser && message.riskFlags && message.riskFlags.length > 0 && (
          <div className="mb-2 px-3 py-2 bg-destructive/10 border border-destructive/30 rounded-lg text-sm">
            <div className="flex items-center gap-1.5 text-destructive font-medium mb-1">
              <AlertTriangle size={13} />
              <span>风险提示</span>
            </div>
            <ul className="text-foreground/70 text-xs space-y-0.5">
              {message.riskFlags.map((flag, i) => (
                <li key={i}>• {flag}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Bubble */}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "bg-primary text-primary-foreground rounded-br-sm"
              : "bg-card border border-border rounded-bl-sm"
          }`}
        >
          {message.status === "streaming" && !message.content ? (
            <LoadingDots />
          ) : isUser ? (
            <span className="whitespace-pre-wrap">{message.content}</span>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
          {message.status === "streaming" && message.content && (
            <span className="inline-block w-0.5 h-4 bg-primary animate-pulse ml-0.5 align-text-bottom" />
          )}
        </div>

        {/* Citations */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-1.5 space-y-0.5">
            {message.citations.map((cite) => (
              <div
                key={cite.index}
                className="flex items-center gap-1.5 text-xs text-muted-foreground"
              >
                <BookOpen size={11} />
                <span>
                  [{cite.index}] {cite.title}
                  {cite.source && ` — ${cite.source}`}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        {!isUser && message.status === "done" && (
          <div className="mt-1.5 flex items-center gap-0.5">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleCopy}>
              <Copy size={12} />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" disabled>
              <RefreshCw size={12} />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" disabled>
              <ThumbsUp size={12} />
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" disabled>
              <ThumbsDown size={12} />
            </Button>
          </div>
        )}

        {/* Intent badge */}
        {!isUser && message.intent && message.status === "done" && (
          <div className="mt-1">
            <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary">
              {message.intent}
            </span>
          </div>
        )}
      </div>

      {isUser && (
        <div className="shrink-0 w-7 h-7 rounded-full bg-primary flex items-center justify-center mt-1">
          <User size={14} className="text-primary-foreground" />
        </div>
      )}
    </motion.div>
  );
}
