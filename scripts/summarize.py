"""
규칙 기반(rule-based) 요약 생성기. 외부 AI 호출 없음, 비용 0원.

- content(무슨 내용인가요): 원문 페이지에서 추출한 본문(body_text)을 최우선으로 사용,
  본문 추출에 실패한 기사만 RSS 스니펫 -> 그마저도 없으면 제목으로 대체
"""
import os
from common import DATA_DIR, load_json, save_json


def split_sentences(text: str):
    # 아주 단순한 규칙: 마침표/물음표/느낌표 기준으로 나눈다 (AI 미사용)
    seps = ["다. ", "요. ", "다.\n", ". "]
    buf = text
    for sep in seps:
        buf = buf.replace(sep, sep.rstrip() + "|")
    parts = [p.strip() for p in buf.split("|") if p.strip()]
    return parts


def build_content(article) -> str:
    body = article.get("body_text", "")
    raw = article.get("summary_raw", "")

    # 1순위: 원문 페이지에서 추출한 실제 본문
    # 2순위: RSS 스니펫 (본문 추출 실패 시)
    # 3순위: 제목 (둘 다 없을 때)
    source_text = body if len(body) >= 40 else raw

    if not source_text or len(source_text) < 5:
        return article["title"]

    sentences = split_sentences(source_text)
    if not sentences:
        return source_text[:200]

    picked = sentences[:3]
    text = " ".join(picked)
    if len(text) > 260:
        text = text[:257].rstrip() + "..."

    if text.strip() == article["title"].strip():
        return article["title"]
    return text


def enrich():
    src = os.path.join(DATA_DIR, "raw_articles.json")
    articles = load_json(src)
    for a in articles:
        a["content_summary"] = build_content(a)
    out = os.path.join(DATA_DIR, "articles_enriched.json")
    save_json(out, articles)
    print(f"요약 생성 완료 {len(articles)}건 -> {out}")
    return articles


if __name__ == "__main__":
    enrich()
