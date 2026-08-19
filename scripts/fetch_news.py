"""
구글 뉴스 RSS에서 기사를 수집한다.
- 카테고리별 검색어(config/categories.json)로 검색해 4개 카테고리 뉴스 수집
- 관심기업별 검색어(config/companies.json)로 검색해 관심기업 뉴스 수집
- 발행일이 최근 WINDOW_HOURS(기본 24시간) 이내인 기사만 남긴다
- 링크 기준으로 중복 제거
"""
import socket
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from common import load_companies, load_categories, clean_html, within_window, save_json, DATA_DIR
import os

RSS_URL = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"

socket.setdefaulttimeout(10)  # 요청 하나가 무한정 멈춰있지 않도록 최대 대기시간 설정


def fetch_query(query: str):
    url = RSS_URL.format(query=quote(query))
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"  [실패] '{query}' 요청 중 예외 발생: {e}")
        return []
    status = getattr(feed, "status", None)
    if getattr(feed, "bozo", 0):
        print(f"  [경고] '{query}' 응답 파싱 이상 (status={status}): {getattr(feed, 'bozo_exception', '')}")
    print(f"  '{query}' -> {len(feed.entries)}건 (status={status})")
    return feed.entries


def parse_pubdate(entry):
    raw = entry.get("published") or entry.get("pubDate")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        return None


def entry_to_article(entry, source_query):
    pub_dt = parse_pubdate(entry)
    if pub_dt is None:
        return None
    source = ""
    if "source" in entry and hasattr(entry.source, "title"):
        source = entry.source.title
    elif " - " in entry.title:
        source = entry.title.rsplit(" - ", 1)[-1]

    title = entry.title
    if source and title.endswith(source):
        title = title[: -(len(source))].rstrip(" -")

    return {
        "title": title.strip(),
        "link": entry.link,
        "source": source.strip(),
        "pub_iso": pub_dt.astimezone(timezone.utc).isoformat(),
        "summary_raw": clean_html(entry.get("summary", "")),
        "matched_by": [source_query],
        "categories": [],
        "companies": [],
    }


def collect():
    now = datetime.now(timezone.utc)
    articles = {}  # link -> article dict

    categories = load_categories()
    companies = load_companies()

    # 1) 카테고리 뉴스 수집
    for cat_name, cat_conf in categories.items():
        for q in cat_conf["queries"]:
            for entry in fetch_query(q):
                art = entry_to_article(entry, q)
                if not art:
                    continue
                pub_dt = datetime.fromisoformat(art["pub_iso"])
                if not within_window(pub_dt, now):
                    continue
                existing = articles.get(art["link"])
                if existing:
                    if cat_name not in existing["categories"]:
                        existing["categories"].append(cat_name)
                else:
                    art["categories"] = [cat_name]
                    articles[art["link"]] = art

    # 2) 관심기업 뉴스 수집 (기존 카테고리 매칭 기사 + 신규 기사 모두 대상으로 기업명 매칭)
    #    - 카테고리 검색으로 이미 모인 기사들 텍스트에서 기업 별칭 매칭
    for art in articles.values():
        haystack = f"{art['title']} {art['summary_raw']}"
        for company, aliases in companies.items():
            if any(alias in haystack for alias in aliases):
                if company not in art["companies"]:
                    art["companies"].append(company)

    #    - 기업명으로 직접 검색해서 카테고리 기사에 안 걸린 관심기업 뉴스도 별도 수집
    for company, aliases in companies.items():
        for entry in fetch_query(company):
            art = entry_to_article(entry, company)
            if not art:
                continue
            pub_dt = datetime.fromisoformat(art["pub_iso"])
            if not within_window(pub_dt, now):
                continue
            existing = articles.get(art["link"])
            if existing:
                if company not in existing["companies"]:
                    existing["companies"].append(company)
            else:
                art["companies"] = [company]
                articles[art["link"]] = art

    # 카테고리도 기업도 매칭 안 된(즉 어느 목적에도 안 맞는) 기사는 제외
    result = [a for a in articles.values() if a["categories"] or a["companies"]]
    result.sort(key=lambda a: a["pub_iso"], reverse=True)
    return result


if __name__ == "__main__":
    articles = collect()
    out_path = os.path.join(DATA_DIR, "raw_articles.json")
    save_json(out_path, articles)
    print(f"수집된 기사 {len(articles)}건 -> {out_path}")
