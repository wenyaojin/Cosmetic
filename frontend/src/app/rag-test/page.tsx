"use client";

import { useEffect, useState } from "react";
import { FileClock, Loader2, Play, RotateCcw, Trash2 } from "lucide-react";
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

const HISTORY_STORAGE_KEY = "rag-test:comparison-history";
const HISTORY_LIMIT = 30;
const REPORT_HISTORY_PREFIX = "report-2026-05-28-agent-rag-vs-raw-10q";
const REPORT_HISTORY_URL = "/rag-eval/2026-05-28-agent-rag-vs-raw-10q/raw_outputs.json";

type CompareResult = {
  message: string;
  citations?: Citation[];
  session_id?: string | null;
  blocked?: boolean;
  risk_flags?: string[];
};

type RagTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
};

type ComparisonHistoryItem = {
  id: string;
  createdAt: string;
  question: string;
  ragTurns: RagTurn[];
  rawTurns: RagTurn[];
  ragSessionId: string | null;
  rawSessionId: string | null;
  ragCitationCount: number;
  rawCitationCount: number;
  ragBlocked?: boolean;
  ragRiskFlags?: string[];
  sourceLabel?: string;
};

type EvalReportResponse = {
  generated_at?: string;
  results?: EvalReportResult[];
};

type EvalReportResult = {
  id?: string;
  type?: string;
  question?: string;
  requested_question?: string;
  agent?: EvalReportSide;
  raw?: EvalReportSide;
};

type EvalReportSide = {
  ended_at?: string;
  response?: {
    message?: string;
    citations?: Citation[];
    session_id?: string | null;
    blocked?: boolean;
    risk_flags?: string[];
  };
};

function mergeHistoryItems(items: ComparisonHistoryItem[]) {
  const seen = new Set<string>();
  return items
    .filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    })
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    .slice(0, HISTORY_LIMIT);
}

export default function RagTestPage() {
  const [question, setQuestion] = useState(EXAMPLE_QUESTIONS[0]);
  const [ragTurns, setRagTurns] = useState<RagTurn[]>([]);
  const [ragSessionId, setRagSessionId] = useState<string | null>(null);
  const [rawTurns, setRawTurns] = useState<RagTurn[]>([]);
  const [rawSessionId, setRawSessionId] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<ComparisonHistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadHistory = async () => {
      let storedItems: ComparisonHistoryItem[] = [];

      try {
        const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
        const parsed = raw ? (JSON.parse(raw) as ComparisonHistoryItem[]) : [];
        if (Array.isArray(parsed)) {
          storedItems = parsed;
        }
      } catch {
        storedItems = [];
      }

      let reportItems: ComparisonHistoryItem[] = [];
      try {
        const res = await fetch(REPORT_HISTORY_URL, { cache: "no-store" });
        if (res.ok) {
          const report = (await res.json()) as EvalReportResponse;
          reportItems = normalizeReportHistory(report);
        }
      } catch {
        reportItems = [];
      }

      if (cancelled) return;

      const next = mergeHistoryItems([...reportItems, ...storedItems]);
      setHistoryItems(next);
      window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next));
    };

    void loadHistory();

    return () => {
      cancelled = true;
    };
  }, []);

  const persistHistory = (item: ComparisonHistoryItem) => {
    setHistoryItems((items) => {
      const next = mergeHistoryItems([
        item,
        ...items.filter((existing) => existing.id !== item.id),
      ]);
      window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const clearHistory = () => {
    window.localStorage.removeItem(HISTORY_STORAGE_KEY);
    setHistoryItems([]);
  };

  const restoreHistory = (item: ComparisonHistoryItem) => {
    setQuestion(item.question);
    setRagTurns(item.ragTurns);
    setRawTurns(item.rawTurns);
    setRagSessionId(item.ragSessionId);
    setRawSessionId(item.rawSessionId);
    setError(null);
  };

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

    const baseRagTurns = [...ragTurns, ragUserTurn];
    const baseRawTurns = [...rawTurns, rawUserTurn];

    setLoading(true);
    setError(null);
    setRagTurns(baseRagTurns);
    setRawTurns(baseRawTurns);

    try {
      const result = await compareChat(text, ragSessionId, rawSessionId);
      const rag = result.rag as CompareResult;
      const raw = result.raw as CompareResult;
      const nextRagSessionId = rag.session_id ?? ragSessionId;
      const nextRawSessionId = raw.session_id ?? rawSessionId;

      if (rag.session_id) {
        setRagSessionId(rag.session_id);
      }
      if (raw.session_id) {
        setRawSessionId(raw.session_id);
      }

      const ragAssistantTurn: RagTurn = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: rag.message,
        citations: rag.citations,
      };
      const rawAssistantTurn: RagTurn = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: raw.message,
        citations: raw.citations,
      };
      const nextRagTurns = [...baseRagTurns, ragAssistantTurn];
      const nextRawTurns = [...baseRawTurns, rawAssistantTurn];

      setRagTurns(nextRagTurns);
      setRawTurns(nextRawTurns);

      persistHistory({
        id: crypto.randomUUID(),
        createdAt: new Date().toISOString(),
        question: text,
        ragTurns: nextRagTurns,
        rawTurns: nextRawTurns,
        ragSessionId: nextRagSessionId,
        rawSessionId: nextRawSessionId,
        ragCitationCount: rag.citations?.length ?? 0,
        rawCitationCount: raw.citations?.length ?? 0,
        ragBlocked: rag.blocked,
        ragRiskFlags: rag.risk_flags,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败");
      setRagTurns((turns) => turns.filter((turn) => turn.id !== ragUserTurn.id));
      setRawTurns((turns) => turns.filter((turn) => turn.id !== rawUserTurn.id));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="h-dvh overflow-y-auto overflow-x-hidden bg-background text-foreground [scrollbar-gutter:stable]">
      <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col px-4 py-4 sm:px-6 lg:px-8">
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

        <section className="grid shrink-0 gap-3 py-3 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            className="min-h-24 resize-none text-sm"
            placeholder="输入要测试的医美问题，或回答左侧 Agent 的追问"
          />
          <aside className="grid min-h-0 gap-3">
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
            <HistoryPanel
              items={historyItems}
              onRestore={restoreHistory}
              onClear={clearHistory}
              disabled={loading}
            />
          </aside>
        </section>

        {error ? (
          <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        <section className="grid min-h-[520px] flex-1 gap-4 lg:min-h-0 lg:overflow-hidden lg:grid-cols-2">
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
    <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card">
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

function HistoryPanel({
  items,
  onRestore,
  onClear,
  disabled,
}: {
  items: ComparisonHistoryItem[];
  onRestore: (item: ComparisonHistoryItem) => void;
  onClear: () => void;
  disabled: boolean;
}) {
  return (
    <section className="min-h-0 rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <FileClock className="size-4" />
          历史结果
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onClear}
          disabled={disabled || !items.length}
          aria-label="清空历史结果"
          title="清空历史结果"
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
      <div className="max-h-48 overflow-y-auto p-2 [scrollbar-gutter:stable]">
        {items.length ? (
          <div className="space-y-2">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onRestore(item)}
                disabled={disabled}
                className="w-full rounded-md border border-border px-3 py-2 text-left transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-60"
              >
                <div className="line-clamp-2 text-xs font-medium leading-5 text-foreground">
                  {item.question}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                  <span>{formatHistoryTime(item.createdAt)}</span>
                  <span>RAG 引用 {item.ragCitationCount}</span>
                  <span>Raw 引用 {item.rawCitationCount}</span>
                  {item.ragBlocked ? <span>已拦截</span> : null}
                  {item.sourceLabel ? <span>{item.sourceLabel}</span> : null}
                  {item.ragRiskFlags?.length ? <span>风险 {item.ragRiskFlags.length}</span> : null}
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="py-6 text-center text-xs text-muted-foreground">
            发送对照后会保存在这里
          </div>
        )}
      </div>
    </section>
  );
}

function formatHistoryTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function normalizeReportHistory(report: EvalReportResponse): ComparisonHistoryItem[] {
  if (!Array.isArray(report.results)) return [];

  return report.results.flatMap((result, index) => {
    const question = result.question ?? result.requested_question;
    const rag = result.agent?.response;
    const raw = result.raw?.response;

    if (!question || !rag?.message || !raw?.message) return [];

    const id = `${REPORT_HISTORY_PREFIX}-${result.id ?? index + 1}`;
    const createdAt =
      result.agent?.ended_at ?? result.raw?.ended_at ?? report.generated_at ?? new Date().toISOString();
    const ragCitations = Array.isArray(rag.citations) ? rag.citations : [];
    const rawCitations = Array.isArray(raw.citations) ? raw.citations : [];

    return [
      {
        id,
        createdAt,
        question,
        ragTurns: [
          {
            id: `${id}-rag-user`,
            role: "user",
            content: question,
          },
          {
            id: `${id}-rag-assistant`,
            role: "assistant",
            content: rag.message,
            citations: ragCitations,
          },
        ],
        rawTurns: [
          {
            id: `${id}-raw-user`,
            role: "user",
            content: question,
          },
          {
            id: `${id}-raw-assistant`,
            role: "assistant",
            content: raw.message,
            citations: rawCitations,
          },
        ],
        ragSessionId: rag.session_id ?? null,
        rawSessionId: raw.session_id ?? null,
        ragCitationCount: ragCitations.length,
        rawCitationCount: rawCitations.length,
        ragBlocked: rag.blocked,
        ragRiskFlags: rag.risk_flags,
        sourceLabel: `报告 ${result.id ?? index + 1}`,
      },
    ];
  });
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
