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
        snippet = (text or title)[:900]
        lines.append(f"[{idx}] 제목: {title}\n본문 일부: {snippet}")
    joined = "\n\n".join(lines)

    prompt = (
        "다음은 여러 마케팅/브랜드 뉴스 기사의 제목과 본문 일부야.\n"
        "각 기사를 한국어 2~3문장으로 요약해줘. 다음 흐름을 지켜줘:\n"
        "1) 무슨 일이 있었는지(도입)\n"
        "2) 구체적으로 어떤 내용인지(중간, 숫자·배경 등 핵심 디테일)\n"
        "3) 그래서 어떻게 됐는지/무엇을 시사하는지(결론) - 본문에 결론성 정보가 없으면 이 문장은 생략해도 돼\n"
        "친근한 대화체(~했어요, ~해요체)로 자연스럽게 써줘. "
        "군더더기 표현 없이 정보 위주로 쓰고, 기사에 없는 내용은 지어내지 마.\n\n"
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
                "max_tokens": 3000,
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

    # 제목과 겹치는 문장은 건너뛰고, 최대 3문장(도입~중간~결론 느낌)까지 사용
    picked = [s for s in sentences[:5] if s.strip() != article["title"].strip()][:3]
    if not picked:
        return article["title"]

    converted = [to_conversational(s) for s in picked]
    text = " ".join(converted)
    if len(text) > 320:
        text = text[:317].rstrip() + "..."
    return text


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
