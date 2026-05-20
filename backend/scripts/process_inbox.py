"""
医美文献处理 Pipeline

功能：
1. 把 _inbox/ 里的原始文献（PDF/Word/网页/Markdown）转成标准化 Markdown
2. 用 LLM 按 schema 改写，加 frontmatter
3. 红线词扫描，输出合规报告
4. 通过的写入 _processed/，需人工复审的写入 _review/

用法：
    cd Q:/Cosmetic/backend
    python -m scripts.process_inbox

    # 或处理单个文件
    python -m scripts.process_inbox --file ../knowledge/_inbox/瑞蓝2号.pdf

依赖：
- markitdown（PDF/Word/HTML 转 MD）
- openai SDK（DeepSeek/GPT 改写）
- pyyaml（红线词库）
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "knowledge" / "_inbox"
PROCESSED = ROOT / "knowledge" / "_processed"
REVIEW = ROOT / "knowledge" / "_review"
META = ROOT / "knowledge" / "_meta"
TEMPLATES = ROOT / "knowledge" / "_templates"

SUPPORTED_EXT = {".pdf", ".docx", ".doc", ".html", ".htm", ".md", ".txt"}


def load_redline() -> dict[str, list[str]]:
    with open(META / "redline.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_template(category: str) -> str:
    tpl = TEMPLATES / f"{category}.md"
    if not tpl.exists():
        tpl = TEMPLATES / "product.md"
    return tpl.read_text(encoding="utf-8")


def convert_to_markdown(src: Path) -> str:
    """用 markitdown 把任意格式转 Markdown."""
    if src.suffix.lower() in {".md", ".txt"}:
        return src.read_text(encoding="utf-8", errors="ignore")

    from markitdown import MarkItDown
    md = MarkItDown()
    result = md.convert(str(src))
    return result.text_content


def scan_redline(text: str, rules: dict) -> dict[str, list[str]]:
    """扫描文本，返回命中的禁词。"""
    hits = {"forbidden": [], "restricted": [], "missing_disclaimer": []}
    for word in rules.get("forbidden", []):
        if word in text:
            hits["forbidden"].append(word)
    for word in rules.get("restricted", []):
        if word in text:
            hits["restricted"].append(word)
    has_any_disclaimer = any(
        d in text for d in rules.get("required_disclaimer", [])
    )
    if not has_any_disclaimer:
        hits["missing_disclaimer"].append("缺少 因人而异 / 仅供参考 等声明")
    return hits


REWRITE_SYSTEM_PROMPT = """你是医美知识库的合规编辑。请把用户给你的原始文献，按下面的模板重新组织为一篇结构化的医美产品/项目文档。

严格要求：
1. 必须严格按模板的章节结构输出
2. 不得使用以下违禁词：根治、永久、最佳、第一、奇迹、保证、零风险、100%、无副作用、立竿见影
3. 涉及效果时必须加 "因人而异" 或 "仅供参考"
4. 价格如有提及，必须标注 "参考价区间，不含麻醉/护理"
5. 适应症 / 禁忌症 / 并发症 三项必须填写
6. 输出 frontmatter 中 NMPA 状态、authority_level 必须根据原文判断填写
7. 找不到的信息写 "暂无资料"，不要编造
8. 用中文输出
9. 直接输出完整 Markdown 文档（含 frontmatter），不要任何解释性文字
"""


async def rewrite_with_llm(raw_text: str, template: str, source_hint: str) -> str:
    """调用 LLM 按模板改写。"""
    from openai import AsyncOpenAI

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    if not api_key:
        raise RuntimeError("请设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY 环境变量")

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    user_prompt = f"""【模板】
{template}

【原始文献来源】
{source_hint}

【原始文献正文】
{raw_text[:15000]}

请按模板输出标准化的医美文档。"""

    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def fill_default_frontmatter(md: str, filename: str) -> str:
    """补全缺失的 frontmatter 字段（last_updated / expire_date 等）。"""
    today = date.today().isoformat()
    expire = (date.today() + timedelta(days=365)).isoformat()

    if not md.startswith("---"):
        return md

    parts = md.split("---", 2)
    if len(parts) < 3:
        return md

    fm_text = parts[1]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return md

    fm.setdefault("title", filename)
    fm.setdefault("last_updated", today)
    fm.setdefault("expire_date", expire)
    fm.setdefault("compliance_review", "pending")
    fm.setdefault("authority_level", 3)

    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    return f"---\n{new_fm}---{parts[2]}"


async def process_file(src: Path, rules: dict, dry_run: bool = False) -> dict:
    """处理单个文件，返回结果报告。"""
    report = {"file": str(src.name), "status": "", "issues": {}, "output": None}

    print(f"\n[处理] {src.name}")

    try:
        raw = convert_to_markdown(src)
    except Exception as e:
        report["status"] = "convert_failed"
        report["issues"] = {"error": str(e)}
        return report

    if len(raw.strip()) < 100:
        report["status"] = "too_short"
        return report

    template = load_template("product")

    try:
        rewritten = await rewrite_with_llm(raw, template, src.name)
    except Exception as e:
        report["status"] = "llm_failed"
        report["issues"] = {"error": str(e)}
        return report

    rewritten = fill_default_frontmatter(rewritten, src.stem)

    hits = scan_redline(rewritten, rules)
    report["issues"] = hits

    if hits["forbidden"]:
        out_dir = REVIEW
        report["status"] = "review_forbidden"
    elif hits["restricted"] or hits["missing_disclaimer"]:
        out_dir = REVIEW
        report["status"] = "review_warning"
    else:
        out_dir = PROCESSED
        report["status"] = "passed"

    if not dry_run:
        out_file = out_dir / f"{src.stem}.md"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(rewritten, encoding="utf-8")
        report["output"] = str(out_file)

    return report


def print_report(reports: list[dict]):
    print("\n" + "=" * 60)
    print("处理报告")
    print("=" * 60)
    counters = {"passed": 0, "review_warning": 0, "review_forbidden": 0, "failed": 0}
    for r in reports:
        st = r["status"]
        if st == "passed":
            counters["passed"] += 1
        elif st == "review_warning":
            counters["review_warning"] += 1
        elif st == "review_forbidden":
            counters["review_forbidden"] += 1
        else:
            counters["failed"] += 1
        flag = {"passed": "[OK]", "review_warning": "[WARN]",
                "review_forbidden": "[BLOCK]"}.get(st, "[FAIL]")
        print(f"{flag} {r['file']:40s} {st}")
        if r["issues"]:
            for k, v in r["issues"].items():
                if v:
                    print(f"     - {k}: {v}")

    print("-" * 60)
    print(f"通过: {counters['passed']}  待复审: {counters['review_warning']}  "
          f"违禁: {counters['review_forbidden']}  失败: {counters['failed']}")
    print(f"\n输出目录:")
    print(f"  通过 → {PROCESSED}")
    print(f"  待复审 → {REVIEW}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, help="处理单个文件")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不写盘")
    args = parser.parse_args()

    rules = load_redline()

    if args.file:
        files = [Path(args.file)]
    else:
        files = [p for p in INBOX.rglob("*") if p.is_file()
                 and p.suffix.lower() in SUPPORTED_EXT]

    if not files:
        print(f"未在 {INBOX} 找到可处理的文献。")
        print(f"支持的格式: {', '.join(sorted(SUPPORTED_EXT))}")
        return

    print(f"待处理: {len(files)} 个文件")

    reports = []
    for f in files:
        r = await process_file(f, rules, dry_run=args.dry_run)
        reports.append(r)

    print_report(reports)


if __name__ == "__main__":
    asyncio.run(main())
