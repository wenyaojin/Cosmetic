"use client";

import { useState } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import { UploadZone, type UploadSubmitValue } from "@/components/preview/UploadZone";
import { BeforeAfter } from "@/components/preview/BeforeAfter";
import { DiagnosisCards } from "@/components/preview/DiagnosisCards";
import { PromptDetails } from "@/components/preview/PromptDetails";
import { ReportView } from "@/components/preview/ReportView";
import { generatePreview, type PreviewResponse } from "@/lib/preview-api";

export default function PreviewPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PreviewResponse | null>(null);

  const handleSubmit = async (v: UploadSubmitValue) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await generatePreview({
        image_base64: v.imageBase64,
        age: v.age,
        gender: v.gender,
        use_fixture: v.useFixture ? "patient_dff3abf1" : null,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const skinPlan = result?.plans.find((p) => p.id === "skin");

  return (
    <div className="h-screen overflow-y-auto bg-background text-foreground">
      <div className="max-w-6xl mx-auto px-6 py-10">
        <header className="border-b border-border pb-6 mb-8">
          <h1 className="text-3xl font-bold">Reveal AI · 术后效果模拟 PoC</h1>
          <p className="text-sm text-muted-foreground mt-2">
            上传正面照 → AI 诊断 27 部位 → 生成治疗方案 → 图像编辑模型模拟术后效果 →
            生成诊断报告
          </p>
        </header>

        <UploadZone onSubmit={handleSubmit} loading={loading} />

        {loading && (
          <div className="mt-8 border border-border rounded-xl bg-card p-8 flex flex-col items-center gap-3">
            <Loader2 size={32} className="animate-spin text-indigo-600" />
            <div className="text-sm text-muted-foreground">
              正在诊断 + 生成术后模拟图...
            </div>
            <div className="text-xs text-muted-foreground">
              预置样例约 2 秒；真实生成约 3-4 分钟
            </div>
          </div>
        )}

        {error && (
          <div className="mt-8 border border-red-300 dark:border-red-800 rounded-xl bg-red-50 dark:bg-red-950/40 p-4 flex items-start gap-3">
            <AlertCircle size={18} className="text-red-600 mt-0.5 shrink-0" />
            <div className="text-sm text-red-800 dark:text-red-200 break-all">
              {error}
            </div>
          </div>
        )}

        {result && skinPlan && (
          <div className="mt-10 flex flex-col gap-10">
            <section>
              <SectionHeader n="①" title="术前 vs 术后模拟" />
              <BeforeAfter
                beforeBase64={result.before_image_base64}
                afterBase64={skinPlan.after_image_base64}
              />
              <div className="mt-3 text-xs text-muted-foreground">
                诊断模型: <b>{result.diagnosis_model}</b> · 诊断延时:{" "}
                <b>{result.diagnosis_latency_sec.toFixed(1)}s</b> · 生图延时:{" "}
                <b>{skinPlan.latency_sec.toFixed(1)}s</b>
              </div>
            </section>

            <section>
              <SectionHeader n="②" title="AI 诊断" />
              <DiagnosisCards
                diagnosis={result.diagnosis}
                focusZones={skinPlan.target_zones}
              />
            </section>

            <section>
              <SectionHeader n="③" title="生成术后图的 Prompt" />
              <PromptDetails
                instruction={skinPlan.instruction}
                planId={skinPlan.id}
                planTitle={skinPlan.title}
                zoneCount={skinPlan.target_zones.length}
                latencySec={skinPlan.latency_sec}
              />
            </section>

            <section>
              <SectionHeader n="④" title="诊断报告" />
              <ReportView markdown={result.report_markdown} />
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function SectionHeader({ n, title }: { n: string; title: string }) {
  return (
    <h2 className="text-xl font-semibold pl-3 border-l-4 border-indigo-600 mb-4 flex items-center gap-2">
      <span className="text-muted-foreground">{n}</span>
      <span>{title}</span>
    </h2>
  );
}
