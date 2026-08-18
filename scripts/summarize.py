"""
규칙 기반(rule-based) 요약 생성기. 외부 AI 호출 없음, 비용 0원.

- content(무슨 내용인가요): RSS 스니펫에서 의미 있는 문장을 최대한 살려 추출
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
    raw = article.get("summary_raw", "")
    if not raw or len(raw) < 5:
        return article["title"]
    sentences = split_sentences(raw)
    if not sentences:
        return raw[:200]
    # 기사 원문 스니펫을 최대한 살려서 3문장까지, 길이는 넉넉하게 허용
    picked = sentences[:3]
    text = " ".join(picked)
    if len(text) > 260:
        text = text[:257].rstrip() + "..."
    # 스니펫이 제목과 거의 같은 경우(요약이 아니라 제목 반복인 경우) 대비
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
