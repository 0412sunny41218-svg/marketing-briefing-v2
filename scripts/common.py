"""공통 유틸리티 함수 모음"""
import json
import re
import os
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(BASE_DIR, "docs")

# 최근 몇 시간 이내 기사만 사용할지 (기본 24시간, 실행 스케줄 오차 감안해 여유 30분 정도만 buffer)
WINDOW_HOURS = int(os.environ.get("BRIEFING_WINDOW_HOURS", "24"))

KST = timezone(timedelta(hours=9))


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_companies():
    return load_json(os.path.join(CONFIG_DIR, "companies.json"))


def load_categories():
    return load_json(os.path.join(CONFIG_DIR, "categories.json"))


def load_major_outlets():
    return set(load_json(os.path.join(CONFIG_DIR, "major_outlets.json")))


def rank_articles(articles, major_outlets=None):
    """
    중요도순 정렬 (AI 미사용, 규칙 기반):
    1) 주요 언론사(major_outlets.json) 기사 우선
    2) 그 안에서는 최신순
    """
    if major_outlets is None:
        major_outlets = load_major_outlets()

    # 안정 정렬(stable sort) 특성을 이용: 최신순으로 먼저 정렬한 뒤,
    # 주요 언론사 여부로 다시 정렬하면 그룹 내부는 최신순이 유지된다.
    sorted_by_recency = sorted(articles, key=lambda a: a.get("pub_iso", ""), reverse=True)
    sorted_by_recency.sort(key=lambda a: 0 if a.get("source") in major_outlets else 1)
    return sorted_by_recency


MAX_PER_CATEGORY = 3    # 카테고리별 최대 노출 건수
MAX_COMPANY_TOTAL = 3   # 관심기업 섹션 전체 최대 노출 건수


def pick_company_articles(articles, max_total=MAX_COMPANY_TOTAL):
    """관심기업별로 골고루 섞어서 상위 max_total건만 뽑는다 (특정 기업 뉴스 쏠림 방지)."""
    by_company = {}
    for a in articles:
        companies = a.get("companies") or []
        if not companies:
            continue
        primary = companies[0]
        by_company.setdefault(primary, []).append(a)

    for company in by_company:
        by_company[company] = dedupe_by_title(rank_articles(by_company[company]))

    picked, seen_links, seen_titles = [], set(), set()
    idx = 0
    companies_order = list(by_company.keys())
    while len(picked) < max_total and companies_order:
        progressed = False
        for company in companies_order:
            bucket = by_company[company]
            if idx < len(bucket):
                art = bucket[idx]
                tkey = normalize_title(art.get("title", ""))
                if art["link"] not in seen_links and tkey not in seen_titles:
                    picked.append(art)
                    seen_links.add(art["link"])
                    if tkey:
                        seen_titles.add(tkey)
                    progressed = True
                if len(picked) >= max_total:
                    break
        idx += 1
        if not progressed:
            break
    return picked


def normalize_title(title: str) -> str:
    """제목 비교용 정규화: 공백/문장부호 제거"""
    if not title:
        return ""
    t = re.sub(r"[\s·\-–—:,\"'“”‘’…!?\.\(\)\[\]]+", "", title)
    return t.lower()


def _title_similarity(a: str, b: str) -> float:
    """0~1 사이 유사도 (difflib 기반, AI 미사용)"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def dedupe_by_title(articles, similarity_threshold: float = 0.72):
    """제목이 사실상 동일/유사한 기사는 하나만 남긴다
    (여러 매체가 같은 소식을 조금씩 다르게 옮겨 쓴 경우 등).
    articles는 이미 원하는 우선순위로 정렬돼 있다고 가정 (먼저 나온 것을 남김)."""
    kept_norms = []
    result = []
    for a in articles:
        key = normalize_title(a.get("title", ""))
        if not key:
            result.append(a)
            continue
        is_dup = any(_title_similarity(key, k) >= similarity_threshold for k in kept_norms)
        if is_dup:
            continue
        kept_norms.append(key)
        result.append(a)
    return result


def clean_html(raw_html: str) -> str:
    """RSS description에 섞인 HTML 태그 제거 + 공백 정리"""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def within_window(pub_dt: datetime, now: datetime = None) -> bool:
    """기사 발행시각이 최근 WINDOW_HOURS 이내인지 확인"""
    if now is None:
        now = datetime.now(timezone.utc)
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
    delta = now - pub_dt
    return timedelta(0) <= delta <= timedelta(hours=WINDOW_HOURS + 1)  # 1시간 여유버퍼


def today_str(now: datetime = None) -> str:
    if now is None:
        now = datetime.now(KST)
    else:
        now = now.astimezone(KST)
    return now.strftime("%Y-%m-%d")
