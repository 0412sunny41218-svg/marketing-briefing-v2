"""
AI 요약 생성기 (Claude Haiku 사용, 실패 시 규칙 기반으로 자동 대체).

- 카테고리/관심기업 기준으로 이미 선별된 기사(최대 MAX_PER_CATEGORY/MAX_COMPANY_TOTAL건)만
  요약 대상으로 삼는다 (전체 기사를 다 요약하면 비용 낭비이므로).
- 선별된 기사들을 한 번의 API 요청에 묶어서 보내 비용/시간을 아낀다.
- ANTHROPIC_API_KEY 환경변수가 없거나 API 호출이 실패하면,
  기존 규칙 기반 방식(원문 문장 1개 + 대화체 변환)으로 자동 대체된다.
"""
import os
import re
import json
import requests

from common import (
    DATA_DIR, load_json, save_json, load_categories,
    rank_articles, dedupe_by_title, pick_company_articles,
    MAX_PER_CATEGORY, MAX_COMPANY_TOTAL,
)

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"


# ---------- 1) 요약 대상 선별 (build_site.py와 동일한 기준) ----------

def select_candidates():
    categories_conf = load_categories()
    articles = load_json(os.path.join(DATA_DIR, "raw_articles.json"))

    grouped = {cat: [] for cat in categories_conf}
    for a in articles:
        for cat in a.get("categories", []):
            if cat in grouped:
                grouped[cat].append(a)
    for cat in grouped:
        grouped[cat] = dedupe_by_title(rank_articles(grouped[cat]))[:MAX_PER_CATEGORY]

    company_articles = [a for a in articles if a.get("companies")]
    company_articles = pick_company_articles(company_articles, MAX_COMPANY_TOTAL)

    selected = {}
    for cat_list in grouped.values():
        for a in cat_list:
            selected[a["link"]] = a
    for a in company_articles:
        selected[a["link"]] = a
    return list(selected.values())


def build_source_text(article) -> str:
    body = article.get("body_text", "")
    raw = article.get("summary_raw", "")
    return body if len(body) >= 40 else raw


# ---------- 2) AI 요약 (Claude Haiku, 여러 건을 한 번에 요청) ----------

def ai_summarize_batch(items):
    """items: [(idx, title, source_text), ...] -> {idx: 요약문}"""
    if not API_KEY or not items:
        return {}

    lines = []
    for idx, title, text in items:
        snippet = (text or title)[:500]
        lines.append(f"[{idx}] 제목: {title}\n본문 일부: {snippet}")
    joined = "\n\n".join(lines)

    prompt = (
        "다음은 여러 마케팅/브랜드 뉴스 기사의 제목과 본문 일부야.\n"
        "각 기사를 한국어 1문장으로, 친근한 대화체(~했어요, ~해요체)로 자연스럽게 요약해줘.\n"
        "군더더기 설명 없이 핵심 내용만 담고, 기사에 없는 내용은 지어내지 마.\n\n"
        f"{joined}\n\n"
        "반드시 아래 JSON 형식으로만 답해줘 (다른 설명 없이 JSON만):\n"
        '{"summaries": {"0": "요약문...", "1": "요약문...", ...}}'
    )

    try:
        resp = requests.post(
            API_URL,
            headers={
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", [])
            if block.get("type") == "text"
        )
        text = re.sub(r"^```json\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
        parsed = json.loads(text)
        return {int(k): v for k, v in parsed.get("summaries", {}).items()}
    except Exception as e:
        print(f"AI 요약 호출 실패, 규칙 기반으로 대체합니다: {e}")
        return {}


# ---------- 3) 규칙 기반 대체 (AI 실패 시에만 사용) ----------

def split_sentences(text: str):
    seps = ["다. ", "요. ", "다.\n", ". "]
    buf = text
    for sep in seps:
        buf = buf.replace(sep, sep.rstrip() + "|")
    return [p.strip() for p in buf.split("|") if p.strip()]


SPECIAL_ENDINGS = [
    ("한다고 밝혔다", "한다고 밝혔어요"),
    ("라고 밝혔다", "라고 밝혔어요"),
    ("고 밝혔다", "고 밝혔어요"),
    ("한다", "해요"),
    ("된다", "돼요"),
    ("이다", "예요"),
    ("있다", "있어요"),
    ("없다", "없어요"),
]


def to_conversational(sentence: str) -> str:
    s = sentence.strip()
    has_period = s.endswith(".")
    if has_period:
        s = s[:-1].strip()
    for formal, casual in SPECIAL_ENDINGS:
        if s.endswith(formal):
            s = s[: -len(formal)] + casual
            break
    else:
        if s.endswith("다"):
            s = s[:-1] + "어요"
    return s + "." if has_period else s


def build_content_fallback(article) -> str:
    source_text = build_source_text(article)
    if not source_text or len(source_text) < 5:
        return article["title"]
    sentences = split_sentences(source_text)
    if not sentences:
        return to_conversational(source_text[:150])
    picked = None
    for s in sentences[:3]:
        if s.strip() != article["title"].strip():
            picked = s
            break
    if picked is None:
        return article["title"]
    if len(picked) > 140:
        picked = picked[:137].rstrip() + "..."
    return to_conversational(picked)


# ---------- 4) 실행 ----------

def enrich():
    selected = select_candidates()

    items = [(i, a["title"], build_source_text(a)) for i, a in enumerate(selected)]
    ai_results = ai_summarize_batch(items)

    for i, a in enumerate(selected):
        summary = ai_results.get(i, "").strip() if ai_results else ""
        a["content_summary"] = summary if summary else build_content_fallback(a)

    out = os.path.join(DATA_DIR, "articles_enriched.json")
    save_json(out, selected)
    mode = "AI 요약" if API_KEY else "규칙 기반(API 키 없음)"
    print(f"요약 생성 완료 {len(selected)}건 [{mode}, AI 성공 {len(ai_results)}건] -> {out}")
    return selected


if __name__ == "__main__":
    enrich()
