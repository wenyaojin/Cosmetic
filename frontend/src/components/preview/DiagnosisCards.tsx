"use client";

import type { DiagnosisPayload, DiagnosisZone } from "@/lib/preview-api";

const TYPE_LABEL: Record<string, string> = {
  PIG: "色素沉着",
  TEX: "肤质粗糙",
  PORE: "毛孔粗大",
  RED: "泛红",
  WR: "细纹",
  VOL: "容量缺失",
  SAG: "松弛下垂",
  DYN: "动态纹",
  FAT: "脂肪堆积",
  PROP: "比例",
};

const SEV_LABEL: Record<string, string> = {
  mild: "轻度",
  mild_moderate: "轻-中度",
  moderate: "中度",
  moderate_severe: "中-重度",
  severe: "重度",
};

const SEV_CLASSES: Record<string, string> = {
  mild: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200",
  mild_moderate: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200",
  moderate: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200",
  moderate_severe: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200",
  severe: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200",
};

interface DiagnosisCardsProps {
  diagnosis: DiagnosisPayload;
  focusZones: string[]; // sub_areas covered by the plan (highlighted)
}

export function DiagnosisCards({ diagnosis, focusZones }: DiagnosisCardsProps) {
  const clj = diagnosis.case_level_judgment ?? {};
  const zones = diagnosis.professional_assessment ?? [];
  const focus = new Set(focusZones);
  const focusedZones = zones.filter((z) => focus.has(z.sub_area));

  return (
    <div className="flex flex-col gap-6">
      <div className="border border-border rounded-xl bg-card p-5">
        <div className="text-sm text-foreground mb-3">{clj.case_summary ?? "—"}</div>
        <div className="text-xs font-semibold text-muted-foreground mb-2">
          主要问题轴 (Main Problem Axes)
        </div>
        <ul className="space-y-1.5">
          {(clj.main_problem_axes ?? []).map((a, i) => (
            <li key={i} className="text-sm text-foreground pl-4 relative">
              <span className="absolute left-0 text-indigo-600 dark:text-indigo-400">▸</span>
              {a}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-muted-foreground mb-3">
          方案目标部位（Zone-Level 诊断）
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {focusedZones.map((z) => (
            <ZoneCard key={z.sub_area} z={z} />
          ))}
        </div>
      </div>
    </div>
  );
}

function ZoneCard({ z }: { z: DiagnosisZone }) {
  const sev = z.severity_level ?? "";
  const sevClass = SEV_CLASSES[sev] ?? "bg-muted text-muted-foreground";
  const gate = z.safety_gate?.triggered ? z.safety_gate?.rule : null;
  return (
    <div className="border border-border rounded-xl bg-card p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="text-base font-semibold">{z.sub_area}</div>
        <div className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${sevClass}`}>
          {SEV_LABEL[sev] ?? sev}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {(z.problem_types ?? []).map((t) => (
          <span
            key={t}
            className="text-[11px] px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-200 font-medium"
          >
            {TYPE_LABEL[t] ?? t}
          </span>
        ))}
      </div>
      <div className="text-xs text-muted-foreground">{z.visible_evidence ?? "—"}</div>
      {z.direction_reasoning && (
        <div className="text-xs italic text-indigo-600 dark:text-indigo-400">
          → {z.direction_reasoning}
        </div>
      )}
      {gate && (
        <div className="text-xs bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-200 rounded-md px-2.5 py-1.5">
          ⚠ 安全提示：{gate}
        </div>
      )}
    </div>
  );
}
