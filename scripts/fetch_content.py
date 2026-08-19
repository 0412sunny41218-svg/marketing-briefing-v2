"""
각 기사의 원문 링크에 실제로 접속해서 본문 텍스트를 규칙 기반으로 추출한다 (AI 미사용).

- 구글 뉴스 RSS의 링크는 실제 기사 주소가 아니라 구글이 감싼 중계 링크다.
  googlenewsdecoder 라이브러리로 실제 언론사 기사 주소를 먼저 풀어낸 뒤 접속한다.
- <p> 태그 중 기자명/저작권 문구/구독 안내/사이드바 기사목록 등 '본문이 아닌 문단'은
  키워드 기반으로 걸러낸다.
- 남은 문단들을 '같은 부모 태그' 기준으로 묶어서, 가장 큰(글자수가 많은) 묶음을
  실제 기사 본문으로 판단한다 (뉴스 사이트는 보통 본문 문단들이 한 덩어리 안에 모여있음).
- 접속 실패/본문 추출 실패 시 조용히 건너뛰고, summarize.py가 RSS 스니펫이나 제목으로 대체 처리한다
"""
import os
import re
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from googlenewsdecoder import gnewsdecoder

from common import DATA_DIR, load_json, save_json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}
TIMEOUT = 8
MAX_WORKERS = 4
MIN_PARAGRAPH_LEN = 30
MAX_BODY_CHARS = 900

# 본문이 아닐 가능성이 높은 문단을 걸러내는 키워드 (기자명/저작권/구독안내/사이드바 목록 등)
BOILERPLATE_PATTERNS = [
    r"저작권자", r"무단\s*전재", r"재배포\s*금지", r"All rights reserved",
    r"Copyright", r"^ⓒ", r"copyright",
    r"기자\s*$", r"특파원\s*$",           # '~~ 기자'로 끝나는 바이라인
    r"구독\s*(하기|해주세요|버튼)?", r"채널\s*추가", r"Google\s*검색에서",
    r"많이\s*본\s*뉴스", r"관련\s*기사", r"오늘의\s*한\s*컷",
    r"^\[.*\]$",                           # 대괄호로만 된 라벨성 문단
]
BOILERPLATE_RE = re.compile("|".join(BOILERPLATE_PATTERNS), re.IGNORECASE)


def is_boilerplate(text: str) -> bool:
    if BOILERPLATE_RE.search(text):
        return True
    # 말줄임표(...)가 여러 번 나오면 여러 헤드라인을 이어붙인 '목록'일 가능성이 높음
    if text.count("...") >= 2 or text.count("…") >= 2:
        return True
    return False


def resolve_real_url(google_link: str) -> str:
    """구글 뉴스 중계 링크 -> 실제 언론사 기사 주소로 변환"""
    try:
        result = gnewsdecoder(google_link, interval=0)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except Exception:
        pass
    return google_link


def extract_body_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "form"]):
        tag.decompose()

    # 문단을 '같은 부모 태그'별로 묶는다 (기사 본문은 보통 한 컨테이너 안에 몰려있음)
    groups = defaultdict(list)
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) < MIN_PARAGRAPH_LEN:
            continue
        if is_boilerplate(text):
            continue
        parent = p.parent
        if parent is None:
            continue
        groups[id(parent)].append(text)

    if not groups:
        return ""

    # 글자수 합이 가장 큰 그룹 = 실제 기사 본문일 가능성이 가장 높음
    best_group = max(groups.values(), key=lambda paras: sum(len(t) for t in paras))

    result, total = [], 0
    for t in best_group:
        result.append(t)
        total += len(t)
        if total > MAX_BODY_CHARS:
            break

    return " ".join(result)


def fetch_one(article):
    try:
        real_url = resolve_real_url(article["link"])
        resp = requests.get(real_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        body = extract_body_text(resp.text)
        if len(body) >= 40:
            article["body_text"] = body
    except Exception:
        pass
    return article


def run():
    path = os.path.join(DATA_DIR, "raw_articles.json")
    articles = load_json(path)

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(fetch_one, a) for a in articles]
        for f in as_completed(futures):
            results.append(f.result())

    link_to_article = {a["link"]: a for a in results}
    ordered = [link_to_article[a["link"]] for a in articles]

    save_json(path, ordered)
    got = sum(1 for a in ordered if a.get("body_text"))
    print(f"본문 추출 완료: {got}/{len(ordered)}건 (실패한 기사는 RSS 스니펫으로 대체됩니다)")


if __name__ == "__main__":
    run()
