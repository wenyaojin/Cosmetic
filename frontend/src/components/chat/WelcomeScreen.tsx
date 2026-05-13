"use client";

import { Sparkles } from "lucide-react";

const PRESET_QUESTIONS = [
  "玻尿酸和自体脂肪填充有什么区别？",
  "热玛吉适合什么年龄做？",
  "我28岁，想改善法令纹，有什么推荐？",
  "光子嫩肤和皮秒有什么区别？",
];

interface WelcomeScreenProps {
  onSelectQuestion: (q: string) => void;
}

export function WelcomeScreen({ onSelectQuestion }: WelcomeScreenProps) {
  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="text-center max-w-lg">
        <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-5">
          <Sparkles size={28} className="text-primary" />
        </div>
        <h2 className="text-xl font-semibold mb-2">AI 医美顾问</h2>
        <p className="text-muted-foreground text-sm mb-8">
          您好！我是 AI 医美咨询助手，可以帮您了解医美项目、分析适合方案、提示风险禁忌。
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-left">
          {PRESET_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => onSelectQuestion(q)}
              className="text-sm text-left px-4 py-3 rounded-xl border border-border
                         hover:bg-accent hover:border-primary/30 transition-all"
            >
              {q}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-8">
          本服务仅供科普参考，不构成医疗建议。
        </p>
      </div>
    </div>
  );
}
