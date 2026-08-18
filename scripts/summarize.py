"""
규칙 기반(rule-based) 요약 생성기. 외부 AI 호출 없음, 비용 0원.

- content(무슨 내용인가요): 원문 페이지에서 추출한 본문(body_text)에서 핵심 문장 1개만 골라
  대화체 말투("~했어요" 등)로 가볍게 바꿔서 보여준다.
  (※ AI가 아니므로 내용을 새로 압축해서 쓰는 '진짜 요약'은 아니고,
     원문 문장 하나를 그대로 가져와 말투만 바꾸는 방식)
"""
import os
import re
from common import DATA_DIR, load_json, save_json


def split_sentences(text: str):
    # 아주 단순한 규칙: 마침표/물음표/느낌표 기준으로 나눈다 (AI 미사용)
    seps = ["다. ", "요. ", "다.\n", ". "]
    buf = text
    for sep in seps:
        buf = buf.replace(sep, sep.rstrip() + "|")
    parts = [p.strip() for p in buf.split("|") if p.strip()]
    return parts


# 문어체 종결어미 -> 대화체 종결어미 (아주 단순한 규칙 기반 치환, 100% 정확하지는 않음)
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
        # 위 특수 규칙에 안 걸리면, 가장 흔한 과거형(-았다/-었다) 처리:
        # '다'로 끝나면 '다'를 떼고 '어요'를 붙인다 (밝혔다 -> 밝혔어요 등)
        if s.endswith("다"):
            s = s[:-1] + "어요"

    return s + "." if has_period else s


def build_content(article) -> str:
    body = article.get("body_text", "")
    raw = article.get("summary_raw", "")

    # 1순위: 원문 페이지에서 추출한 실제 본문 / 2순위: RSS 스니펫 / 3순위: 제목
    source_text = body if len(body) >= 40 else raw

    if not source_text or len(source_text) < 5:
        return article["title"]

    sentences = split_sentences(source_text)
    if not sentences:
        return to_conversational(source_text[:150])

    # 문장 1개만 사용 (제목과 완전히 겹치는 경우는 다음 문장으로)
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
