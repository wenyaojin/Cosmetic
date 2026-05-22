"""
Collect open PubMed literature metadata for the Phase 1 RAG plan.

The script writes standardized Markdown documents under ``knowledge/_processed``.
It stores PubMed titles, citation metadata, abstracts, and source URLs instead of
copying paywalled full text.

Usage:
    cd Q:/Cosmetic/backend
    python -m scripts.collect_pubmed_plan --limit-per-topic 2
    python -m scripts.collect_pubmed_plan --dry-run
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "knowledge" / "_processed" / "pubmed"
NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass(frozen=True)
class Topic:
    slug: str
    title: str
    category: str
    sub_category: str
    tags: list[str]
    query: str


TOPICS = [
    Topic(
        slug="facial-danger-zones-filler",
        title="面部填充注射危险区与血管风险",
        category="anatomy",
        sub_category="面部解剖",
        tags=["面部解剖", "注射禁区", "血管栓塞", "填充剂"],
        query='((face OR facial) AND (danger zone* OR vascular OR artery OR anatomy) AND filler* AND injection)',
    ),
    Topic(
        slug="periorbital-filler-anatomy",
        title="眶周与泪沟填充解剖风险",
        category="anatomy",
        sub_category="眶周解剖",
        tags=["眶周", "泪沟", "面部解剖", "填充剂"],
        query='((periorbital OR tear trough OR infraorbital) AND filler* AND (anatomy OR complication OR vascular))',
    ),
    Topic(
        slug="nasal-filler-vascular-risk",
        title="鼻部填充血管风险",
        category="anatomy",
        sub_category="鼻部解剖",
        tags=["鼻部", "注射禁区", "血管风险", "填充剂"],
        query='((nasal OR nose OR rhinoplasty) AND filler* AND (vascular OR necrosis OR blindness OR complication))',
    ),
    Topic(
        slug="hyaluronic-acid-fillers-complications",
        title="透明质酸填充剂并发症与处理",
        category="complication",
        sub_category="玻尿酸",
        tags=["透明质酸", "填充剂", "并发症", "注射填充"],
        query='("hyaluronic acid"[Title/Abstract] AND filler*[Title/Abstract] AND complication*[Title/Abstract] AND (aesthetic OR cosmetic))',
    ),
    Topic(
        slug="hyaluronidase-filler-reversal",
        title="透明质酸酶处理填充剂相关并发症",
        category="complication",
        sub_category="玻尿酸",
        tags=["透明质酸酶", "玻尿酸", "并发症处理", "注射填充"],
        query='(hyaluronidase AND hyaluronic acid filler AND (complication OR vascular occlusion OR necrosis))',
    ),
    Topic(
        slug="filler-vascular-occlusion",
        title="填充剂血管栓塞与缺血处理",
        category="complication",
        sub_category="注射并发症",
        tags=["血管栓塞", "缺血", "填充剂", "急救"],
        query='(filler injection AND (vascular occlusion OR vascular compromise OR ischemia OR necrosis))',
    ),
    Topic(
        slug="delayed-filler-nodules",
        title="填充剂迟发结节与炎症反应",
        category="complication",
        sub_category="注射并发症",
        tags=["迟发结节", "炎症反应", "填充剂", "并发症"],
        query='(dermal filler AND (delayed nodule OR inflammatory nodule OR granuloma OR biofilm))',
    ),
    Topic(
        slug="botulinum-toxin-aesthetic-safety",
        title="肉毒毒素美容应用安全性",
        category="procedure",
        sub_category="肉毒素",
        tags=["肉毒素", "安全性", "注射填充"],
        query='("botulinum toxin"[Title/Abstract] AND (aesthetic OR cosmetic) AND (safety OR adverse))',
    ),
    Topic(
        slug="botulinum-toxin-blepharoptosis",
        title="肉毒毒素相关眼睑下垂预防与处理",
        category="complication",
        sub_category="肉毒素",
        tags=["肉毒素", "眼睑下垂", "并发症"],
        query='("botulinum toxin" AND (blepharoptosis OR ptosis) AND (cosmetic OR aesthetic OR injection))',
    ),
    Topic(
        slug="botulinum-toxin-masseter",
        title="肉毒毒素咬肌注射与下面部轮廓",
        category="procedure",
        sub_category="肉毒素",
        tags=["肉毒素", "咬肌", "瘦脸", "下面部轮廓"],
        query='("botulinum toxin" AND masseter AND (aesthetic OR cosmetic OR contouring))',
    ),
    Topic(
        slug="calcium-hydroxylapatite-fillers",
        title="羟基磷灰石钙填充剂应用与安全性",
        category="product",
        sub_category="再生类填充",
        tags=["羟基磷灰石钙", "再生填充", "填充剂"],
        query='("calcium hydroxylapatite" AND filler AND (aesthetic OR cosmetic OR safety))',
    ),
    Topic(
        slug="poly-l-lactic-acid-fillers",
        title="聚左旋乳酸填充剂应用与安全性",
        category="product",
        sub_category="再生类填充",
        tags=["聚左旋乳酸", "童颜针", "再生填充"],
        query='("poly-L-lactic acid" AND filler AND (aesthetic OR cosmetic OR safety OR complication))',
    ),
    Topic(
        slug="polynucleotide-skin-rejuvenation",
        title="多核苷酸皮肤年轻化证据",
        category="procedure",
        sub_category="水光/修复",
        tags=["多核苷酸", "皮肤年轻化", "水光"],
        query='(polynucleotide AND (skin rejuvenation OR aesthetic OR cosmetic OR dermatology))',
    ),
    Topic(
        slug="platelet-rich-plasma-aesthetic",
        title="富血小板血浆美容皮肤应用",
        category="procedure",
        sub_category="再生治疗",
        tags=["PRP", "皮肤年轻化", "再生治疗"],
        query='("platelet-rich plasma" AND (skin rejuvenation OR aesthetic OR cosmetic dermatology))',
    ),
    Topic(
        slug="laser-ipl-adverse-events",
        title="激光与强脉冲光治疗不良反应",
        category="complication",
        sub_category="光电美肤",
        tags=["激光", "强脉冲光", "并发症", "光电美肤"],
        query='((laser OR "intense pulsed light") AND dermatology AND (adverse OR complication) AND cosmetic)',
    ),
    Topic(
        slug="ipl-photorejuvenation",
        title="强脉冲光嫩肤疗效与安全性",
        category="procedure",
        sub_category="强脉冲光",
        tags=["IPL", "嫩肤", "光电美肤"],
        query='("intense pulsed light" AND (photorejuvenation OR photoaging OR cosmetic) AND safety)',
    ),
    Topic(
        slug="fractional-co2-acne-scars",
        title="点阵二氧化碳激光治疗痤疮瘢痕",
        category="procedure",
        sub_category="点阵激光",
        tags=["点阵激光", "CO2", "痤疮瘢痕", "光电美肤"],
        query='("fractional CO2 laser" AND acne scar AND (efficacy OR safety OR adverse))',
    ),
    Topic(
        slug="picosecond-laser-pigmentation",
        title="皮秒激光色素性问题治疗",
        category="procedure",
        sub_category="皮秒激光",
        tags=["皮秒", "色斑", "色素", "光电美肤"],
        query='("picosecond laser" AND (pigmentation OR melasma OR tattoo OR lentigines) AND dermatology)',
    ),
    Topic(
        slug="q-switched-laser-melasma",
        title="调Q激光与黄褐斑治疗风险",
        category="procedure",
        sub_category="调Q激光",
        tags=["调Q", "黄褐斑", "反黑", "光电美肤"],
        query='("Q-switched" AND laser AND melasma AND (adverse OR safety OR recurrence))',
    ),
    Topic(
        slug="laser-hair-removal-safety",
        title="激光脱毛疗效与安全性",
        category="procedure",
        sub_category="脱毛激光",
        tags=["激光脱毛", "半导体", "翠绿宝石", "光电美肤"],
        query='("laser hair removal" AND (safety OR adverse OR efficacy) AND dermatology)',
    ),
    Topic(
        slug="vascular-lasers-rosacea-telangiectasia",
        title="血管激光治疗玫瑰痤疮与毛细血管扩张",
        category="procedure",
        sub_category="血管激光",
        tags=["血管激光", "玫瑰痤疮", "红血丝", "光电美肤"],
        query='((pulsed dye laser OR Nd:YAG OR vascular laser) AND (rosacea OR telangiectasia) AND dermatology)',
    ),
    Topic(
        slug="radiofrequency-skin-rejuvenation",
        title="射频皮肤年轻化疗效与安全性",
        category="procedure",
        sub_category="射频",
        tags=["射频", "抗衰", "皮肤年轻化", "光电美肤"],
        query='(radiofrequency AND "skin rejuvenation" AND (aesthetic OR cosmetic) AND safety)',
    ),
    Topic(
        slug="radiofrequency-microneedling-acne-scars",
        title="黄金微针射频治疗痤疮瘢痕",
        category="procedure",
        sub_category="黄金微针",
        tags=["射频微针", "黄金微针", "痤疮瘢痕", "光电美肤"],
        query='("radiofrequency microneedling" AND acne scar AND (efficacy OR safety))',
    ),
    Topic(
        slug="hifu-skin-tightening",
        title="聚焦超声紧肤疗效与安全性",
        category="procedure",
        sub_category="超声抗衰",
        tags=["HIFU", "超声", "紧肤", "抗衰"],
        query='("high-intensity focused ultrasound" AND (skin tightening OR facial lifting OR aesthetic) AND safety)',
    ),
    Topic(
        slug="photodynamic-therapy-acne",
        title="光动力治疗痤疮疗效与风险",
        category="procedure",
        sub_category="光动力",
        tags=["光动力", "痤疮", "皮肤管理"],
        query='("photodynamic therapy" AND acne AND (efficacy OR safety OR adverse))',
    ),
    Topic(
        slug="chemical-peeling-safety",
        title="化学焕肤适应症与安全性",
        category="procedure",
        sub_category="皮肤管理",
        tags=["化学焕肤", "果酸", "水杨酸", "皮肤管理"],
        query='("chemical peel" AND dermatology AND (safety OR adverse OR acne OR melasma))',
    ),
]


def fetch_xml(endpoint: str, params: dict[str, str | int]) -> ET.Element:
    query = urllib.parse.urlencode(params)
    url = f"{NCBI_BASE}/{endpoint}?{query}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = resp.read()
    return ET.fromstring(data)


def search_pubmed(query: str, limit: int) -> list[str]:
    root = fetch_xml(
        "esearch.fcgi",
        {
            "db": "pubmed",
            "term": query,
            "retmode": "xml",
            "retmax": limit,
            "sort": "relevance",
        },
    )
    return [node.text for node in root.findall(".//Id") if node.text]


def fetch_details(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    root = fetch_xml(
        "efetch.fcgi",
        {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        },
    )
    return [parse_article(article) for article in root.findall(".//PubmedArticle")]


def text_at(node: ET.Element, path: str, default: str = "") -> str:
    found = node.find(path)
    if found is None or found.text is None:
        return default
    return normalize_text(found.text)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def compliance_safe_text(text: str) -> str:
    """Neutralize marketing-redline phrases that may appear inside abstracts."""
    replacements = {
        "100%": "all reported",
        "No adverse events were reported": "The abstract reports no adverse events in that study sample",
    }
    cleaned = text
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return cleaned


def parse_article(article: ET.Element) -> dict:
    pmid = text_at(article, ".//PMID")
    medline = article.find(".//MedlineCitation")
    article_node = article.find(".//Article")
    journal_node = article.find(".//Journal")

    title = text_at(article, ".//ArticleTitle", f"PubMed {pmid}")
    journal = text_at(journal_node, "Title") if journal_node is not None else ""
    year = (
        text_at(article, ".//PubDate/Year")
        or text_at(article, ".//ArticleDate/Year")
        or text_at(article, ".//PubDate/MedlineDate")[:4]
    )
    abstract_parts = []
    if article_node is not None:
        for abstract in article_node.findall(".//AbstractText"):
            label = abstract.attrib.get("Label", "")
            text = normalize_text("".join(abstract.itertext()))
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)

    authors = []
    if medline is not None:
        for author in medline.findall(".//Author")[:6]:
            last = text_at(author, "LastName")
            fore = text_at(author, "ForeName")
            collective = text_at(author, "CollectiveName")
            name = collective or " ".join(p for p in [fore, last] if p)
            if name:
                authors.append(name)

    return {
        "pmid": pmid,
        "title": title,
        "journal": journal,
        "year": year,
        "authors": authors,
        "abstract": compliance_safe_text("\n\n".join(abstract_parts)) or "暂无公开摘要。",
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
    }


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    cleaned = re.sub(r"\s+", "-", cleaned).strip("-.")
    return cleaned[:120] or "pubmed-document"


def frontmatter(topic: Topic, article: dict) -> str:
    today = date.today()
    meta = {
        "title": f"{topic.title}：{article['title']}",
        "category": topic.category,
        "sub_category": topic.sub_category,
        "tags": topic.tags + ["PubMed", article.get("year", "")],
        "authority_level": 4,
        "source_type": "academic",
        "source": "PubMed",
        "source_url": article["url"],
        "source_doc": f"{article.get('journal', '')} {article.get('year', '')}".strip(),
        "pmid": article["pmid"],
        "nmpa_status": "N/A",
        "nmpa_no": "N/A",
        "published_at": f"{article.get('year', '')}-01-01" if str(article.get("year", "")).isdigit() else None,
        "last_updated": today.isoformat(),
        "expire_date": (today + timedelta(days=365)).isoformat(),
        "reviewed_by": "pending",
        "compliance_review": "pending",
    }
    meta = {k: v for k, v in meta.items() if v not in (None, "")}
    return yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()


def article_markdown(topic: Topic, article: dict) -> str:
    authors = "、".join(article["authors"]) if article["authors"] else "暂无资料"
    citation = f"{authors}. {article['title']}. {article['journal']}. {article['year']}. PMID: {article['pmid']}."
    fm = frontmatter(topic, article)
    return f"""---
{fm}
---

# {topic.title}：{article['title']}

## 一、基本信息
- 主题：{topic.title}
- 文献题名：{article['title']}
- 期刊：{article['journal'] or '暂无资料'}
- 年份：{article['year'] or '暂无资料'}
- PMID：{article['pmid']}
- 来源链接：{article['url']}

## 二、作用机制 / 原理
本文献摘要涉及 {topic.sub_category} 相关机制、适用场景或风险因素。以下内容基于 PubMed 公开摘要整理，完整结论需结合原文和临床指南复核。

## 三、适应症
暂无资料。请结合获批适应症、产品说明书、设备说明书及医生面诊评估判断。

## 四、禁忌症
### 绝对禁忌
暂无资料。

### 相对禁忌
暂无资料。孕哺期、活动性感染、瘢痕体质、自身免疫疾病活动期、凝血异常或抗凝用药等情况需咨询专业医生。

## 五、操作流程
暂无资料。具体操作流程应以医疗机构规范、产品说明书、设备说明书和医生评估为准。

## 六、效果预期与维持时间
效果和维持时间存在个体差异，仅供参考。本文献摘要不能替代个体化面诊结论。

## 七、常见并发症与处理
本文献与「{topic.title}」相关，可作为风险教育与并发症识别的参考线索。实际处理需由专业医生根据症状、部位、严重程度和时间窗判断。

## 八、术前评估清单
- 核对治疗项目、产品或设备是否合规。
- 评估过敏史、用药史、既往医美史、感染情况和基础疾病。
- 充分沟通预期效果、替代方案、恢复期和潜在风险。
- 签署知情同意，并保留产品批号或设备治疗参数记录。

## 九、术后护理
暂无资料。一般需遵循医生给出的清洁、防晒、避免高温刺激、复诊观察等建议。

## 十、价格区间（参考）
暂无资料。价格仅能作为参考价区间，且通常不含麻醉/护理/复诊费用。

## 十一、与同类产品对比
暂无资料。对比时应同时评估适应症、风险、证据等级、获批状态、医生经验和个人条件。

## 十二、常见问答（FAQ）
**Q：这篇文献可以直接作为个人治疗建议吗？**  
A：不可以。它只能作为科普和 RAG 检索参考，具体方案需咨询专业医生。

## 摘要
{article['abstract']}

## 参考文献
- {citation} {article['url']}
"""


def write_article(topic: Topic, article: dict, dry_run: bool) -> Path:
    topic_dir = OUT_DIR / topic.slug
    filename = f"{article['pmid']}-{sanitize_filename(article['title'])}.md"
    out_file = topic_dir / filename
    if not dry_run:
        topic_dir.mkdir(parents=True, exist_ok=True)
        out_file.write_text(article_markdown(topic, article), encoding="utf-8")
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect PubMed documents for the Phase 1 RAG plan")
    parser.add_argument("--limit-per-topic", type=int, default=2, help="Documents per topic")
    parser.add_argument("--dry-run", action="store_true", help="Print matches without writing files")
    args = parser.parse_args()

    total = 0
    seen_pmids: set[str] = set()
    for topic in TOPICS:
        pmids = [pmid for pmid in search_pubmed(topic.query, args.limit_per_topic * 2) if pmid not in seen_pmids]
        articles = fetch_details(pmids[: args.limit_per_topic])
        print(f"\n{topic.title}: {len(articles)} article(s)")
        for article in articles:
            if article["pmid"] in seen_pmids:
                continue
            seen_pmids.add(article["pmid"])
            out_file = write_article(topic, article, args.dry_run)
            total += 1
            print(f"  - PMID {article['pmid']} -> {out_file}")
        time.sleep(0.34)

    action = "Would write" if args.dry_run else "Wrote"
    print(f"\n{action} {total} standardized PubMed document(s).")


if __name__ == "__main__":
    main()
