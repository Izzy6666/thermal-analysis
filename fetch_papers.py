from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

API_URL = "https://api.openalex.org/works"
DATA_FILE = Path("data/papers.json")

# 这些词既覆盖常见热分析技术，也尽量把“应用”而不是纯理论论文筛出来。
SEARCH_QUERY = (
    '("thermal analysis" OR calorimetry OR DSC OR '
    'thermogravimetric OR TGA OR "dynamic mechanical analysis" OR '
    'DMA OR "thermomechanical analysis" OR TMA) AND '
    '(battery OR polymer OR composite OR adhesive OR packaging OR '
    'recycling OR pharmaceutical OR food OR biomaterial OR '
    '"phase change material" OR electronics OR safety OR degradation)'
)

TECHNIQUE_PATTERNS: dict[str, list[str]] = {
    "DSC": [
        r"\bdsc\b",
        r"differential scanning calorimetr",
        r"calorimetr",
    ],
    "TGA": [
        r"\btga\b",
        r"thermogravimet",
    ],
    "DMA": [
        r"\bdma\b",
        r"dynamic mechanical analys",
    ],
    "TMA": [
        r"\btma\b",
        r"thermomechanical analys",
    ],
    "STA": [
        r"\bsta\b",
        r"simultaneous thermal analys",
    ],
    "TGA-MS": [
        r"tga[\s\-–]?ms",
        r"thermogravimet.*mass spectrom",
    ],
    "TGA-FTIR": [
        r"tga[\s\-–]?ftir",
        r"thermogravimet.*infrared",
    ],
    "Flash DSC": [
        r"flash dsc",
        r"fast scanning calorimetr",
    ],
}

CATEGORY_PATTERNS: dict[str, list[str]] = {
    "新能源与储能": [
        "battery", "electrolyte", "electrode", "thermal runaway",
        "separator", "lithium", "sodium-ion", "supercapacitor",
        "hydrogen storage", "phase change material",
    ],
    "电子与封装": [
        "electronic", "packaging", "underfill", "adhesive", "oca",
        "semiconductor", "dielectric", "solder", "printed circuit",
    ],
    "高分子与复合材料": [
        "polymer", "composite", "resin", "elastomer", "rubber",
        "thermoset", "thermoplastic", "fiber",
    ],
    "循环利用与可持续材料": [
        "recycling", "recycled", "waste", "biodegradable",
        "bio-based", "circular", "pyrolysis",
    ],
    "医药与生物材料": [
        "pharmaceutical", "drug", "polymorph", "protein",
        "biomaterial", "hydrogel", "tissue",
    ],
    "食品与脂质": [
        "food", "fat", "lipid", "chocolate", "starch",
        "crystallization", "emulsion",
    ],
    "热安全与失效分析": [
        "safety", "failure", "degradation", "aging", "ageing",
        "flammability", "fire", "thermal stability",
    ],
}

APPLICATION_HINTS: dict[str, str] = {
    "新能源与储能": "可关注材料筛选、热安全评价、相变储能或电池失效分析。",
    "电子与封装": "可关注固化、Tg、热膨胀、界面应力与器件可靠性。",
    "高分子与复合材料": "可关注配方比较、结构—性能关系、固化和老化评价。",
    "循环利用与可持续材料": "可关注回收料鉴别、组成定量、热解路线和批次稳定性。",
    "医药与生物材料": "可关注晶型、相容性、变性、冻干或材料稳定性。",
    "食品与脂质": "可关注脂肪结晶、相变、氧化稳定性与加工窗口。",
    "热安全与失效分析": "可关注分解起始、反应顺序、放热风险与寿命预测。",
}


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """把 OpenAlex 的 abstract_inverted_index 恢复成普通文本。"""
    if not inverted_index:
        return ""

    positions: list[tuple[int, str]] = []
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions.append((index, word))

    positions.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positions)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]


def extractive_summary(abstract: str, max_sentences: int = 3) -> str:
    """
    不调用 AI 的抽取式概括：
    优先保留研究目的、方法、结果或结论意味较强的句子。
    """
    sentences = split_sentences(abstract)
    if not sentences:
        return "OpenAlex 暂未提供摘要。"

    keywords = (
        "aim", "purpose", "investigate", "evaluate", "develop",
        "method", "using", "result", "show", "demonstrate",
        "found", "conclude", "suggest", "indicate", "reveal",
        "application", "performance", "stability",
    )

    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        lower = sentence.lower()
        score = sum(1 for keyword in keywords if keyword in lower)

        # 首句通常交代背景或目的，适当加权。
        if index == 0:
            score += 2
        # 过短句通常信息量有限。
        if len(sentence) < 45:
            score -= 1

        scored.append((score, index, sentence))

    selected = sorted(
        sorted(scored, reverse=True)[:max_sentences],
        key=lambda item: item[1],
    )
    return " ".join(sentence for _, _, sentence in selected)


def detect_techniques(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for technique, patterns in TECHNIQUE_PATTERNS.items():
        if any(re.search(pattern, lower) for pattern in patterns):
            found.append(technique)
    return found or ["热分析"]


def detect_categories(text: str) -> list[str]:
    lower = text.lower()
    scores: list[tuple[int, str]] = []

    for category, keywords in CATEGORY_PATTERNS.items():
        score = sum(1 for keyword in keywords if keyword in lower)
        if score:
            scores.append((score, category))

    scores.sort(reverse=True)
    return [category for _, category in scores[:2]] or ["其他潜在应用"]


def build_application_hint(categories: list[str]) -> str:
    hints = [
        APPLICATION_HINTS[category]
        for category in categories
        if category in APPLICATION_HINTS
    ]
    return " ".join(hints) or "建议结合论文摘要判断其可迁移的检测或研发场景。"


def load_existing() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return {"updated_at": "", "papers": []}

    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"updated_at": "", "papers": []}


def fetch_recent_works() -> list[dict[str, Any]]:
    start_date = (date.today() - timedelta(days=30)).isoformat()
    contact_email = os.getenv("OPENALEX_EMAIL", "").strip()

    params = {
        "search": SEARCH_QUERY,
        "filter": (
            f"from_publication_date:{start_date},"
            "has_abstract:true,"
            "type:article|review"
        ),
        "sort": "publication_date:desc",
        "per-page": 50,
        "select": (
            "id,doi,title,publication_date,primary_location,"
            "authorships,abstract_inverted_index,topics,type"
        ),
    }
    if contact_email:
        params["mailto"] = contact_email

    response = requests.get(API_URL, params=params, timeout=45)
    response.raise_for_status()
    return response.json().get("results", [])


def normalise_work(work: dict[str, Any]) -> dict[str, Any]:
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    title = (work.get("title") or "Untitled").strip()
    combined_text = f"{title}\n{abstract}"

    authors = []
    for authorship in work.get("authorships", [])[:8]:
        name = (authorship.get("author") or {}).get("display_name")
        if name:
            authors.append(name)

    location = work.get("primary_location") or {}
    source = location.get("source") or {}

    doi = work.get("doi") or ""
    landing_page = location.get("landing_page_url") or doi or work.get("id")

    techniques = detect_techniques(combined_text)
    categories = detect_categories(combined_text)

    return {
        "id": work.get("id"),
        "title": title,
        "authors": authors,
        "publication_date": work.get("publication_date") or "",
        "journal": source.get("display_name") or "未注明来源",
        "doi": doi,
        "url": landing_page,
        "abstract": abstract,
        "summary": extractive_summary(abstract),
        "techniques": techniques,
        "categories": categories,
        "application_hint": build_application_hint(categories),
        "source_note": "题录与摘要来自 OpenAlex；概括为程序抽取式摘要，不使用 AI。",
    }


def main() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    existing = load_existing()
    existing_papers = existing.get("papers", [])
    existing_by_id = {
        paper.get("id"): paper
        for paper in existing_papers
        if paper.get("id")
    }

    for work in fetch_recent_works():
        paper = normalise_work(work)
        if paper["id"]:
            existing_by_id[paper["id"]] = paper

    papers = sorted(
        existing_by_id.values(),
        key=lambda paper: paper.get("publication_date", ""),
        reverse=True,
    )[:300]

    output = {
        "updated_at": date.today().isoformat(),
        "query": SEARCH_QUERY,
        "papers": papers,
    }

    DATA_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Updated {len(papers)} papers.")


if __name__ == "__main__":
    main()