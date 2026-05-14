"use client";

import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/types/chat";

interface SidebarProps {
  open: boolean;
  onClose?: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const {
    conversations,
    currentConversationId,
    loadConversation,
    newConversation,
    removeConversation,
  } = useChatStore();

  const handleSelect = (conv: Conversation) => {
    if (conv.id === currentConversationId) return;
    loadConversation(conv.id);
    onClose?.();
  };

  const handleNew = () => {
    newConversation();
    onClose?.();
  };

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 bg-black/40 z-30 lg:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={cn(
          "fixed lg:relative z-40 top-0 left-0 h-full w-64 bg-sidebar border-r border-sidebar-border flex flex-col transition-transform duration-200",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        <div className="p-3 border-b border-sidebar-border">
          <Button
            variant="outline"
            className="w-full justify-start gap-2 text-sm"
            onClick={handleNew}
          >
            <Plus size={14} />
            新建对话
          </Button>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-0.5">
            {conversations.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-8">
                暂无对话记录
              </p>
            )}
            {conversations.map((conv) => (
              <div
                key={conv.id}
                className={cn(
                  "group w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-colors cursor-pointer",
                  conv.id === currentConversationId
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "hover:bg-sidebar-accent/50 text-sidebar-foreground"
                )}
                onClick={() => handleSelect(conv)}
              >
                <MessageSquare size={14} className="shrink-0 opacity-50" />
                <span className="truncate flex-1">{conv.title || "新对话"}</span>
                <button
                  className="shrink-0 opacity-0 group-hover:opacity-100 hover:text-destructive transition-opacity"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeConversation(conv.id);
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </ScrollArea>
      </aside>
    </>
  );
}
