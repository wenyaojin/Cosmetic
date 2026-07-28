"""Render a Markdown diagnosis report from a diagnosis JSON.

Ported from tmp/render_report.py — differences from the tmp version:
- No hardcoded patient metadata; age/gender/patient_id passed in as params
- Doctor gold-label comparison page dropped (new-user path has no gold labels)
- Returns a Markdown string instead of writing to a file
- Cover page renders age/gender line only if both provided
"""
from __future__ import annotations

from datetime import date
from typing import Any

_SEV_CN = {
    "none_or_maintenance": "无明显 / 维护型",
    "mild": "轻度",
    "mild_moderate": "轻度-中度",
    "moderate": "中度",
    "moderate_severe": "中度偏中重度",
    "severe": "中重度",
    "pending_45_or_side_view": "需 45°/侧面确认",
    "pending_dynamic_view": "需动态视角确认",
}
_SEV_EMOJI = {
    "none_or_maintenance": "🟢",
    "mild": "🟡",
    "mild_moderate": "🟠",
    "moderate": "🔴",
    "moderate_severe": "🔴",
    "severe": "🔴",
    "pending_45_or_side_view": "🔵",
    "pending_dynamic_view": "🔵",
}
_PRIO_CN = {"high": "高", "medium": "中", "low": "低"}
_SEV_ORDER_FOR_RANKING = [
    "severe", "moderate_severe", "moderate", "mild_moderate", "mild",
    "pending_45_or_side_view", "pending_dynamic_view", "none_or_maintenance",
]

_GENDER_CN = {"female": "女性", "male": "男性"}


def _rank_zones_by_severity(zones: list[dict]) -> list[dict]:
    def key(z):
        sev = z.get("severity_level", "none_or_maintenance")
        try:
            sev_rank = _SEV_ORDER_FOR_RANKING.index(sev)
        except ValueError:
            sev_rank = 99
        prio_rank = {"high": 0, "medium": 1, "low": 2}.get(z.get("priority"), 3)
        return (sev_rank, prio_rank)
    return sorted(zones, key=key)


def _pick_top_problems(zones: list[dict], n: int = 3) -> list[dict]:
    actionable = [
        z for z in zones
        if z.get("severity_level") not in (
            "none_or_maintenance", "pending_45_or_side_view", "pending_dynamic_view"
        )
    ]
    return _rank_zones_by_severity(actionable)[:n]


def _pick_pending_zones(zones: list[dict]) -> list[dict]:
    return [z for z in zones if str(z.get("severity_level", "")).startswith("pending")]


def _pick_not_recommended(zones: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for z in zones:
        for item in z.get("not_recommended", []) or []:
            item = item.strip()
            if item and item not in seen:
                seen.add(item)
                out.append(item)
    return out[:6]


def _page_1_cover(age: int | None, gender: str | None) -> str:
    lines = ["# 医美 AI 智能诊断报告", ""]
    if age is not None and gender:
        gender_cn = _GENDER_CN.get(gender, gender)
        lines.append(f"**年龄 / 性别**：{age} 岁 / {gender_cn}")
    elif age is not None:
        lines.append(f"**年龄**：{age} 岁")
    elif gender:
        lines.append(f"**性别**：{_GENDER_CN.get(gender, gender)}")
    lines.extend([
        "**评估类型**：术前初评（正面照）",
        f"**报告日期**：{date.today().isoformat()}",
        "",
        "*本报告由 AI 生成，基于医生审校的诊断规则与既往病例训练。"
        "仅供医生 review 参考，非最终医疗建议。*",
    ])
    return "\n".join(lines)


def _page_2_summary(clj: dict, top_problems: list[dict]) -> str:
    axes_bullets = "\n".join(f"- {a}" for a in clj.get("main_problem_axes", [])[:5])
    out = f"""# 一、核心判断

{clj.get('case_summary', '（无总判断）')}

## 主要问题轴

{axes_bullets}

## 建议输出风格

{clj.get('output_style_guidance', '（无风格建议）')}

---

# 二、本次需要关注的 3 个主问题

"""
    if not top_problems:
        return out + "*本次未发现需要主动处理的问题（所有部位为维护型或需补充角度确认）*\n"

    for i, z in enumerate(top_problems, 1):
        sev = z.get("severity_level")
        emoji = _SEV_EMOJI.get(sev, "•")
        out += f"""### {emoji} 问题 {i}：{z['sub_area']}

- **严重程度**：{_SEV_CN.get(sev, sev)}
- **优先级**：{_PRIO_CN.get(z.get('priority'), '-')}
- **观察**：{(z.get('visible_evidence') or '-')[:100]}
- **建议方向**：{(z.get('direction_reasoning') or '-')[:120]}

"""
    return out


def _page_3_notrec_pending(not_recommended: list[str], pending: list[dict]) -> str:
    out = "# 三、本次**不建议**的项目\n\n"
    if not_recommended:
        for item in not_recommended:
            out += f"- {item}\n"
    else:
        out += "*无*\n"

    out += "\n---\n\n# 四、需要补充的信息\n\n"
    if pending:
        out += "以下部位**仅正面照无法可靠判断**，需要补充其他视角/动态照片才能给出确定意见：\n\n"
        for z in pending:
            sev_type = "45°/侧面照" if "45_or_side" in z.get("severity_level", "") else "动态表情照"
            out += f"- **{z['sub_area']}** — 需 {sev_type}\n"
    else:
        out += "*本次判断均基于正面照即可完成，无需补充其他视角*\n"
    return out


def _page_5_full_table(zones: list[dict]) -> str:
    out = "# 五、27 部位完整诊断表\n\n"
    out += "| 部位 | AI 判定 | 优先级 | AI 观察 |\n|---|---|---|---|\n"
    for z in zones:
        sev = z.get("severity_level", "-")
        out += (
            f"| {z['sub_area']} "
            f"| {_SEV_CN.get(sev, sev)} "
            f"| {_PRIO_CN.get(z.get('priority'), '-')} "
            f"| {(z.get('visible_evidence') or '-')[:60]} |\n"
        )
    return out


def _page_6_footer(model_meta: dict[str, Any], zones: list[dict]) -> str:
    return """# 六、免责声明

本报告由大语言模型基于医生审校规则自动生成，仅供**医生 review 参考**。
- 不构成医疗诊断或治疗建议
- 仅基于正面照判断，最终方案需结合 45°/侧面/动态照及触诊
- 治疗方案须由持证医生根据完整临床评估决定
"""


def render(
    diagnosis: dict,
    model_meta: dict[str, Any] | None = None,
    age: int | None = None,
    gender: str | None = None,
) -> str:
    """Build the full 5-page Markdown report.

    Args:
      diagnosis:   the diagnosis JSON (case_level_judgment + professional_assessment)
      model_meta:  {model, latency_sec, usage, estimated_cost_cny} — optional,
                   rendered on footer page. Missing fields render as 0/unknown.
      age:         optional; rendered on cover if provided
      gender:      optional; "female"|"male"; rendered on cover if provided
    """
    zones = diagnosis.get("professional_assessment", [])
    clj = diagnosis.get("case_level_judgment", {})
    meta = model_meta or {}

    top_problems = _pick_top_problems(zones, n=3)
    pending = _pick_pending_zones(zones)
    not_rec = _pick_not_recommended(zones)

    pages = [
        _page_1_cover(age, gender),
        _page_2_summary(clj, top_problems),
        _page_3_notrec_pending(not_rec, pending),
        _page_5_full_table(zones),
        _page_6_footer(meta, zones),
    ]
    return "\n\n---\n\n".join(pages)
