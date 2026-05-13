const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export async function fetchConversations(): Promise<
  { id: string; title: string; created_at: string; updated_at: string }[]
> {
  const res = await fetch(`${API_BASE}/api/v1/sessions`);
  if (!res.ok) return [];
  const json = await res.json();
  return json.sessions ?? [];
}

export async function fetchMessages(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/v1/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function* streamMessage(
  message: string,
  sessionId?: string
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API_BASE}/api/v1/agent/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId ?? null }),
  });

  if (!res.ok) throw new Error(`API error: ${res.status}`);
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let currentEvent = "message";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const raw = line.slice(6);
        try {
          yield { event: currentEvent, data: JSON.parse(raw) };
        } catch {
          yield { event: currentEvent, data: { text: raw } };
        }
        currentEvent = "message";
      }
    }
  }
}
