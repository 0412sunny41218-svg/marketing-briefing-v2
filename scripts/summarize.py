"""
규칙 기반(rule-based) 요약 생성기. 외부 AI 호출 없음, 비용 0원.

- content(무슨 내용인가요): RSS 스니펫에서 의미 있는 문장 1~2개 추출
- why(왜 중요한가요): 카테고리별 고정 템플릿 + 매칭된 관심기업이 있으면 문구 추가
- tip(참고하면 좋은 점): 카테고리별 고정 템플릿
"""
import os
from common import load_categories, DATA_DIR, load_json, save_json

WHY_TEMPLATES = {
    "브랜드·캠페인": "브랜드가 시장에 어떤 메시지를 던지고 있는지 보여주는 사례예요. 캠페인 기획이나 톤앤매너를 잡을 때 참고할 만합니다.",
    "콘텐츠·미디어": "콘텐츠가 소비되는 방식과 채널 전략이 어떻게 바뀌고 있는지 보여줘요. 콘텐츠 기획안을 짤 때 트렌드 참고용으로 좋습니다.",
    "소비자·트렌드": "요즘 소비자들이 무엇에 반응하는지 알 수 있는 신호예요. 타깃 인사이트를 잡을 때 유용합니다.",
    "업계·비즈니스": "마케팅·광고 업계 전반의 흐름을 보여주는 소식이에요. 산업 동향 파악에 도움이 됩니다.",
}

TIP_TEMPLATES = {
    "브랜드·캠페인": "비슷한 캠페인을 기획한다면, 이 사례의 메시지 구조와 채널 조합을 벤치마킹해보세요.",
    "콘텐츠·미디어": "콘텐츠 포맷이나 배포 채널을 정할 때 이 사례의 접근 방식을 참고해보세요.",
    "소비자·트렌드": "타깃 오디언스의 최근 관심사를 리서치할 때 이 트렌드를 키워드로 검색해보세요.",
    "업계·비즈니스": "관련 업계 리포트나 후속 기사를 찾아보면 좀 더 깊이 있는 맥락을 파악할 수 있어요.",
}

COMPANY_WHY_SUFFIX = " 관심기업으로 등록한 '{company}' 관련 소식이라 경쟁사·업계 동향 파악에 특히 도움이 될 거예요."
COMPANY_TIP = "관심기업 소식은 놓치지 말고 팀 채널에 공유해두면 나중에 회고할 때 유용해요."


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
        return raw[:120]
    picked = sentences[:2]
    text = " ".join(picked)
    if len(text) > 160:
        text = text[:157].rstrip() + "..."
    return text


def build_why(article) -> str:
    cats = article.get("categories") or []
    base = WHY_TEMPLATES.get(cats[0]) if cats else None
    if not base:
        base = "관심기업으로 등록한 기업이 언급된 기사예요."
    companies = article.get("companies") or []
    if companies:
        base += COMPANY_WHY_SUFFIX.format(company=companies[0])
    return base


def build_tip(article) -> str:
    cats = article.get("categories") or []
    tip = TIP_TEMPLATES.get(cats[0]) if cats else None
    if not tip:
        tip = COMPANY_TIP
    if article.get("companies") and cats:
        tip += " " + COMPANY_TIP
    return tip


def enrich():
    src = os.path.join(DATA_DIR, "raw_articles.json")
    articles = load_json(src)
    for a in articles:
        a["content_summary"] = build_content(a)
        a["why_it_matters"] = build_why(a)
        a["tip"] = build_tip(a)
    out = os.path.join(DATA_DIR, "articles_enriched.json")
    save_json(out, articles)
    print(f"요약 생성 완료 {len(articles)}건 -> {out}")
    return articles


if __name__ == "__main__":
    enrich()
