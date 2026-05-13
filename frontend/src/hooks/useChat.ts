"use client";

import { useCallback } from "react";
import { useChatStore } from "@/stores/chat-store";
import { streamMessage } from "@/lib/api";

export function useChat() {
  const {
    messages,
    currentConversationId,
    isLoading,
    addMessage,
    updateMessage,
    appendToken,
    setLoading,
    setCurrentConversation,
    addConversation,
    updateConversationTitle,
  } = useChatStore();

  const send = useCallback(
    async (text: string) => {
      if (isLoading) return;

      const userMsg = {
        id: crypto.randomUUID(),
        role: "user" as const,
        content: text,
        timestamp: Date.now(),
        status: "done" as const,
      };

      const assistantId = crypto.randomUUID();
      const assistantMsg = {
        id: assistantId,
        role: "assistant" as const,
        content: "",
        timestamp: Date.now(),
        status: "streaming" as const,
      };

      addMessage(userMsg);
      addMessage(assistantMsg);
      setLoading(true);

      try {
        for await (const event of streamMessage(
          text,
          currentConversationId ?? undefined
        )) {
          switch (event.event) {
            case "status": {
              const sid = event.data.session_id as string | undefined;
              if (sid && !currentConversationId) {
                setCurrentConversation(sid);
                const title = text.length > 20 ? text.slice(0, 20) + "…" : text;
                addConversation({
                  id: sid,
                  title,
                  createdAt: Date.now(),
                  updatedAt: Date.now(),
                });
              } else if (sid && currentConversationId) {
                updateConversationTitle(currentConversationId,
                  text.length > 20 ? text.slice(0, 20) + "…" : text
                );
              }
              if (event.data.blocked) {
                updateMessage(assistantId, {
                  content:
                    (event.data.reply as string) || "该问题暂不支持回答。",
                  status: "done",
                  blocked: true,
                });
                setLoading(false);
                return;
              }
              break;
            }
            case "citations":
              updateMessage(assistantId, {
                citations: event.data.citations as any,
              });
              break;

            case "token":
              appendToken(assistantId, (event.data.text as string) ?? "");
              break;

            case "done":
              updateMessage(assistantId, {
                status: "done",
                intent: (event.data.intent as string) ?? null,
                riskFlags: (event.data.risk_flags as string[]) ?? [],
              });
              break;

            case "error":
              updateMessage(assistantId, {
                content: "抱歉，出现了错误，请稍后重试。",
                status: "error",
              });
              break;
          }
        }
      } catch {
        updateMessage(assistantId, {
          content: "网络错误，请检查连接后重试。",
          status: "error",
        });
      } finally {
        setLoading(false);
      }
    },
    [
      addMessage,
      updateMessage,
      appendToken,
      setLoading,
      setCurrentConversation,
      addConversation,
      updateConversationTitle,
    ]
  );

  return { messages, isLoading, send };
}
