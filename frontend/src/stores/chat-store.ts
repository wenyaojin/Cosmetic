import { create } from "zustand";
import { fetchMessages } from "@/lib/api";
import type { Message, Conversation } from "@/types/chat";

interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  messages: Message[];
  isLoading: boolean;

  setConversations: (convs: Conversation[]) => void;
  setCurrentConversation: (id: string | null) => void;
  addConversation: (conv: Conversation) => void;
  updateConversationTitle: (id: string, title: string) => void;
  setMessages: (msgs: Message[]) => void;
  addMessage: (msg: Message) => void;
  updateMessage: (id: string, patch: Partial<Message>) => void;
  appendToken: (id: string, token: string) => void;
  setLoading: (v: boolean) => void;
  newConversation: () => void;
  loadConversation: (id: string) => Promise<void>;
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  currentConversationId: null,
  messages: [],
  isLoading: false,

  setConversations: (convs) => set({ conversations: convs }),
  setCurrentConversation: (id) => set({ currentConversationId: id }),
  addConversation: (conv) =>
    set((s) => ({
      conversations: [conv, ...s.conversations.filter((c) => c.id !== conv.id)],
    })),
  updateConversationTitle: (id, title) =>
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === id ? { ...c, title, updatedAt: Date.now() } : c
      ),
    })),
  setMessages: (msgs) => set({ messages: msgs }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateMessage: (id, patch) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    })),
  appendToken: (id, token) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + token } : m
      ),
    })),
  setLoading: (v) => set({ isLoading: v }),
  newConversation: () =>
    set({ currentConversationId: null, messages: [] }),
  loadConversation: async (id: string) => {
    set({ currentConversationId: id, messages: [], isLoading: true });
    try {
      const data = await fetchMessages(id);
      const history: Message[] = (data.messages ?? []).map(
        (m: { role: string; content: string }, i: number) => ({
          id: `hist-${id}-${i}`,
          role: m.role as "user" | "assistant",
          content: m.content,
          timestamp: Date.now(),
          status: "done" as const,
        })
      );
      set({ messages: history });
    } catch {
      set({ messages: [] });
    } finally {
      set({ isLoading: false });
    }
  },
}));
