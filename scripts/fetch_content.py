"""
각 기사의 원문 링크에 실제로 접속해서 본문 텍스트를 규칙 기반으로 추출한다 (AI 미사용).

- <p> 태그들을 모아서, 너무 짧은 문단(광고/네비게이션 문구일 가능성 높음)은 제외
- 앞부분 문단들을 이어붙여 body_text로 저장
- 접속 실패/본문 추출 실패 시 조용히 건너뛰고, summarize.py가 RSS 스니펫이나 제목으로 대체 처리한다
"""
import os
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import DATA_DIR, load_json, save_json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
TIMEOUT = 6
MAX_WORKERS = 8
MIN_PARAGRAPH_LEN = 25   # 이보다 짧은 문단은 광고/메뉴 문구일 가능성이 높아 제외
MAX_BODY_CHARS = 500     # 문단을 이어붙이는 총 길이 상한 (앞부분만 있으면 충분)


def extract_body_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "form"]):
        tag.decompose()

    paragraphs = []
    total_len = 0
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if len(text) >= MIN_PARAGRAPH_LEN:
            paragraphs.append(text)
            total_len += len(text)
        if total_len > MAX_BODY_CHARS:
            break

    return " ".join(paragraphs)


def fetch_one(article):
    try:
        resp = requests.get(article["link"], headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        body = extract_body_text(resp.text)
        if len(body) >= 40:
            article["body_text"] = body
    except Exception:
        pass  # 실패하면 본문 없이 넘어감 -> summarize.py가 RSS 스니펫/제목으로 대체
    return article


def run():
    path = os.path.join(DATA_DIR, "raw_articles.json")
    articles = load_json(path)

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(fetch_one, a) for a in articles]
        for f in as_completed(futures):
            results.append(f.result())

    # 원래 순서(최신순) 유지해서 저장
    link_to_article = {a["link"]: a for a in results}
    ordered = [link_to_article[a["link"]] for a in articles]

    save_json(path, ordered)
    got = sum(1 for a in ordered if a.get("body_text"))
    print(f"본문 추출 완료: {got}/{len(ordered)}건 (실패한 기사는 RSS 스니펫으로 대체됩니다)")


if __name__ == "__main__":
    run()
