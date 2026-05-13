export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  status: "sending" | "streaming" | "done" | "error";
  feedback?: "up" | "down";
  citations?: Citation[];
  intent?: string | null;
  riskFlags?: string[];
  blocked?: boolean;
  suggestions?: string[];
}

export interface Citation {
  index: number;
  title: string;
  source: string;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
}
