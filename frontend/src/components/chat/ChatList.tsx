"use client";

import { useEffect, useRef } from "react";
import { ChatMessage } from "./ChatMessage";
import { WelcomeScreen } from "./WelcomeScreen";
import type { Message } from "@/types/chat";

interface ChatListProps {
  messages: Message[];
  onSelectQuestion: (q: string) => void;
}

export function ChatList({ messages, onSelectQuestion }: ChatListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, messages[messages.length - 1]?.content]);

  if (messages.length === 0) {
    return <WelcomeScreen onSelectQuestion={onSelectQuestion} />;
  }

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto min-h-0">
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
