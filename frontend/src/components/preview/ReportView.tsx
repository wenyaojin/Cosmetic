"use client";

import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MarkdownRenderer } from "@/components/common/MarkdownRenderer";

interface ReportViewProps {
  markdown: string;
}

export function ReportView({ markdown }: ReportViewProps) {
  const handleDownload = () => {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const today = new Date().toISOString().slice(0, 10);
    a.download = `diagnosis_report_${today}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="border border-border rounded-xl bg-card">
      <div className="flex items-center justify-between px-5 py-3 border-b border-border">
        <div className="text-sm font-semibold text-foreground">诊断报告</div>
        <Button onClick={handleDownload} size="sm" variant="outline" className="gap-2">
          <Download size={14} />
          下载 .md
        </Button>
      </div>
      <div className="px-6 py-5 max-h-[600px] overflow-y-auto prose prose-sm dark:prose-invert max-w-none">
        <MarkdownRenderer content={markdown} />
      </div>
    </div>
  );
}
