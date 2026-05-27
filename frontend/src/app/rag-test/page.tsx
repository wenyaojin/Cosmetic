"use client";

import { useState } from "react";
import { Loader2, Play, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MarkdownRenderer } from "@/components/common/MarkdownRenderer";
import { compareChat } from "@/lib/api";
import type { Citation } from "@/types/chat";

const EXAMPLE_QUESTIONS = [
  "玻尿酸填充后皮肤发白、发紫、疼痛，应该怎么办？",
  "泪沟填充有哪些风险？什么人不适合做？",
  "肉毒素打咬肌会不会导致脸垮或者咀嚼无力？",
  "皮秒激光治疗黄褐斑安全吗？会不会反黑？",
];

type CompareResult = {
  message: string;
  citations?: Citation[];
  session_id?: string | null;
};

type RagTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
};

export default function RagTestPage() {
  const [question, setQuestion] = useState(EXAMPLE_QUESTIONS[0]);
  const [ragTurns, setRagTurns] = useState<RagTurn[]>([]);
  const [ragSessionId, setRagSessionId] = useState<string | null>(null);
  const [rawTurns, setRawTurns] = useState<RagTurn[]>([]);
  const [rawSessionId, setRawSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const reset = () => {
    setQuestion(EXAMPLE_QUESTIONS[0]);
    setRagTurns([]);
    setRagSessionId(null);
    setRawTurns([]);
    setRawSessionId(null);
    setError(null);
  };

  const runCompare = async () => {
    const text = question.trim();
    if (!text || loading) return;

    const ragUserTurn: RagTurn = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    const rawUserTurn: RagTurn = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };

    setLoading(true);
    setError(null);
    setRagTurns((turns) => [...turns, ragUserTurn]);
    setRawTurns((turns) => [...turns, rawUserTurn]);

    try {
      const result = await compareChat(text, ragSessionId, rawSessionId);
      const rag = result.rag as CompareResult;
      const raw = result.raw as CompareResult;
      if (rag.session_id) {
        setRagSessionId(rag.session_id);
      }
      if (raw.session_id) {
        setRawSessionId(raw.session_id);
      }

      setRagTurns((turns) => [
        ...turns,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: rag.message,
          citations: rag.citations,
        },
      ]);
      setRawTurns((turns) => [
        ...turns,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: raw.message,
          citations: raw.citations,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败");
      setRagTurns((turns) => turns.filter((turn) => turn.id !== ragUserTurn.id));
      setRawTurns((turns) => turns.filter((turn) => turn.id !== rawUserTurn.id));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex shrink-0 flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">RAG 对照测试</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              左侧是可连续追问的 Agent + RAG 会话，右侧是当前输入的纯模型回答。
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={reset} disabled={loading}>
              <RotateCcw />
              重置
            </Button>
            <Button onClick={runCompare} disabled={loading || !question.trim()}>
              {loading ? <Loader2 className="animate-spin" /> : <Play />}
              发送并对照
            </Button>
          </div>
        </header>

        <section className="grid shrink-0 gap-3 py-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <Textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            className="min-h-24 resize-none text-sm"
            placeholder="输入要测试的医美问题，或回答左侧 Agent 的追问"
          />
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
            {EXAMPLE_QUESTIONS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setQuestion(item)}
                className="rounded-md border border-border px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                {item}
              </button>
            ))}
          </div>
        </section>

        {error ? (
          <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        <section className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
          <RagConversationPane
            title="带 Agent + RAG"
            subtitle="完整编排、追问、检索知识库"
            turns={ragTurns}
            sessionId={ragSessionId}
            loading={loading}
          />
          <RagConversationPane
            title="纯模型"
            subtitle="无 Agent 编排、无 RAG 检索"
            turns={rawTurns}
            sessionId={rawSessionId}
            loading={loading}
          />
        </section>
      </div>
    </main>
  );
}

function PaneShell({
  title,
  subtitle,
  loading,
  children,
}: {
  title: string;
  subtitle: string;
  loading: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-[520px] flex-col overflow-hidden rounded-lg border border-border bg-card lg:h-[calc(100vh-260px)]">
      <div className="shrink-0 border-b border-border px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">{title}</h2>
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          </div>
          {loading ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-scroll px-4 py-4 [scrollbar-gutter:stable]">
        {children}
      </div>
    </div>
  );
}

function RagConversationPane({
  title,
  subtitle,
  turns,
  sessionId,
  loading,
}: {
  title: string;
  subtitle: string;
  turns: RagTurn[];
  sessionId: string | null;
  loading: boolean;
}) {
  return (
    <PaneShell
      title={title}
      subtitle={`${subtitle}${sessionId ? ` · ${sessionId.slice(0, 8)}` : ""}`}
      loading={loading}
    >
      {turns.length ? (
        <div className="space-y-4 text-sm leading-6">
          {turns.map((turn) => (
            <div
              key={turn.id}
              className={turn.role === "user" ? "flex justify-end" : "flex justify-start"}
            >
              <div
                className={
                  turn.role === "user"
                    ? "max-w-[86%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"
                    : "max-w-[92%] rounded-lg border border-border bg-background px-3 py-2 text-sm"
                }
              >
                <MarkdownRenderer content={turn.content} />
                {turn.role === "assistant" ? <Citations citations={turn.citations ?? []} /> : null}
              </div>
            </div>
          ))}
          {loading ? <div className="text-xs text-muted-foreground">Agent 正在回复...</div> : null}
        </div>
      ) : (
        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
          发送后显示多轮对话
        </div>
      )}
    </PaneShell>
  );
}

function Citations({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;

  return (
    <div className="mt-3 border-t border-border pt-3">
      <h3 className="mb-2 text-xs font-semibold text-muted-foreground">引用资料</h3>
      <ol className="space-y-2 text-xs text-muted-foreground">
        {citations.map((citation) => (
          <li key={`${citation.index}-${citation.title}`}>
            <span className="font-medium text-foreground">[{citation.index}] </span>
            {citation.title}
            {citation.source ? <span> · {citation.source}</span> : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
