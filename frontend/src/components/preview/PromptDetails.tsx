"use client";

interface PromptDetailsProps {
  instruction: string;
  planId: string;
  planTitle: string;
  zoneCount: number;
  latencySec: number;
}

export function PromptDetails({
  instruction,
  planId,
  planTitle,
  zoneCount,
  latencySec,
}: PromptDetailsProps) {
  return (
    <details className="border border-border rounded-xl bg-card px-5 py-4 group">
      <summary className="cursor-pointer text-sm font-semibold text-indigo-600 dark:text-indigo-400 list-none flex items-center justify-between">
        <span>展开：生成术后图使用的 Prompt</span>
        <span className="text-xs text-muted-foreground group-open:hidden">▶</span>
        <span className="text-xs text-muted-foreground hidden group-open:inline">▼</span>
      </summary>
      <pre className="mt-4 bg-slate-900 text-slate-100 rounded-lg p-4 text-xs leading-relaxed whitespace-pre-wrap font-mono overflow-x-auto">
        {instruction}
      </pre>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span>
          方案: <b>{planId}</b> · {planTitle}
        </span>
        <span>
          覆盖部位: <b>{zoneCount}</b>
        </span>
        <span>
          生成延时: <b>{latencySec.toFixed(1)}s</b>
        </span>
      </div>
    </details>
  );
}
