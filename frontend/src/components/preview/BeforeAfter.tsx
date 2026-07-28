"use client";

interface BeforeAfterProps {
  beforeBase64: string;
  afterBase64: string;
}

export function BeforeAfter({ beforeBase64, afterBase64 }: BeforeAfterProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <figure className="rounded-xl overflow-hidden border border-border bg-card">
        <img
          src={`data:image/png;base64,${beforeBase64}`}
          alt="术前"
          className="w-full block"
        />
        <figcaption className="px-4 py-3 bg-red-50 dark:bg-red-950/30 text-sm font-semibold text-foreground flex items-center justify-between">
          <span>术前 · 原图</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-900/50 text-red-800 dark:text-red-200">
            Before
          </span>
        </figcaption>
      </figure>
      <figure className="rounded-xl overflow-hidden border border-border bg-card">
        <img
          src={`data:image/png;base64,${afterBase64}`}
          alt="术后模拟"
          className="w-full block"
        />
        <figcaption className="px-4 py-3 bg-green-50 dark:bg-green-950/30 text-sm font-semibold text-foreground flex items-center justify-between">
          <span>术后模拟 · 皮肤表层改善方案</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/50 text-green-800 dark:text-green-200">
            After
          </span>
        </figcaption>
      </figure>
    </div>
  );
}
