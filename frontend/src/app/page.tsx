"use client";

import { useState, useEffect } from "react";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { ChatList } from "@/components/chat/ChatList";
import { ChatInput } from "@/components/chat/ChatInput";
import { useChat } from "@/hooks/useChat";
import { useChatStore } from "@/stores/chat-store";
import { fetchConversations } from "@/lib/api";

export default function Home() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { messages, isLoading, send } = useChat();
  const setConversations = useChatStore((s) => s.setConversations);

  useEffect(() => {
    fetchConversations().then((sessions) => {
      setConversations(
        sessions.map((s) => ({
          id: s.id,
          title: s.title,
          createdAt: new Date(s.created_at).getTime(),
          updatedAt: new Date(s.updated_at).getTime(),
        }))
      );
    });
  }, [setConversations]);

  return (
    <div className="h-full flex">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col min-w-0">
        <Header onToggleSidebar={() => setSidebarOpen((v) => !v)} />
        <ChatList messages={messages} onSelectQuestion={send} />
        <ChatInput onSend={send} disabled={isLoading} />
      </div>
    </div>
  );
}
