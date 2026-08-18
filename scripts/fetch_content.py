"""
각 기사의 원문 링크에 실제로 접속해서 본문 텍스트를 규칙 기반으로 추출한다 (AI 미사용).

- 구글 뉴스 RSS의 링크는 실제 기사 주소가 아니라 구글이 감싼 중계 링크다.
  googlenewsdecoder 라이브러리로 실제 언론사 기사 주소를 먼저 풀어낸 뒤 접속한다.
- <p> 태그들을 모아서, 너무 짧은 문단(광고/네비게이션 문구일 가능성 높음)은 제외
- 앞부분 문단들을 이어붙여 body_text로 저장
- 접속 실패/본문 추출 실패 시 조용히 건너뛰고, summarize.py가 RSS 스니펫이나 제목으로 대체 처리한다
"""
import os
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
MAX_WORKERS = 4   # 구글 디코딩 자체가 요청을 여러 번 하므로 동시 개수를 낮게 유지
MIN_PARAGRAPH_LEN = 25
MAX_BODY_CHARS = 500


def resolve_real_url(google_link: str) -> str:
    """구글 뉴스 중계 링크 -> 실제 언론사 기사 주소로 변환"""
    try:
        result = gnewsdecoder(google_link, interval=0)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except Exception:
        pass
    return google_link  # 실패하면 원래 링크로라도 시도


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
        real_url = resolve_real_url(article["link"])
        resp = requests.get(real_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
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

    link_to_article = {a["link"]: a for a in results}
    ordered = [link_to_article[a["link"]] for a in articles]

    save_json(path, ordered)
    got = sum(1 for a in ordered if a.get("body_text"))
    print(f"본문 추출 완료: {got}/{len(ordered)}건 (실패한 기사는 RSS 스니펫으로 대체됩니다)")


if __name__ == "__main__":
    run()
