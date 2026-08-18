"""
data/articles_enriched.json + config/categories.json 을 이용해
docs/ 폴더에 정적 HTML 사이트를 생성한다 (GitHub Pages 배포용).

- docs/index.html            : 홈 (오늘 브리핑 버튼 + 최근 업데이트)
- docs/briefing/YYYY-MM-DD.html : 그날의 브리핑 상세
- docs/archive/index.html    : 전체 브리핑 목록
- data/history.json          : 브리핑 발행 이력 (다음 실행에서도 유지되도록 커밋됨)
"""
import os
import shutil
from datetime import datetime, timedelta

from jinja2 import Environment, FileSystemLoader
from common import (
    BASE_DIR, DATA_DIR, DOCS_DIR, KST,
    load_categories, load_json, save_json, today_str,
)

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def label_for(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.year}년 {dt.month}월 {dt.day}일 ({WEEKDAY_KO[dt.weekday()]})"


def short_label_for(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.month}월 {dt.day}일"


def build_highlight(company_count, cat_counts):
    parts = []
    if company_count:
        parts.append(f"관심기업 {company_count}건")
    top_cats = sorted(cat_counts.items(), key=lambda x: -x[1])[:2]
    for cat, cnt in top_cats:
        if cnt:
            parts.append(f"{cat} {cnt}건")
    return " · ".join(parts) if parts else "오늘은 새 소식이 없어요"


def main():
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    categories_conf = load_categories()

    articles = load_json(os.path.join(DATA_DIR, "articles_enriched.json"))
    date_str = today_str()
    label = label_for(date_str)

    company_articles = [a for a in articles if a.get("companies")]
    grouped = {cat: [] for cat in categories_conf}
    for a in articles:
        for cat in a.get("categories", []):
            if cat in grouped:
                grouped[cat].append(a)

    # ---- docs 폴더 준비 ----
    os.makedirs(os.path.join(DOCS_DIR, "briefing"), exist_ok=True)
    os.makedirs(os.path.join(DOCS_DIR, "archive"), exist_ok=True)
    static_dest = os.path.join(DOCS_DIR, "static")
    if os.path.exists(static_dest):
        shutil.rmtree(static_dest)
    shutil.copytree(STATIC_DIR, static_dest)

    # ---- 오늘 브리핑 상세 페이지 ----
    briefing_tpl = env.get_template("briefing.html")
    briefing_html = briefing_tpl.render(
        date=date_str,
        label=label,
        categories=categories_conf,
        grouped=grouped,
        company_articles=company_articles,
    )
    with open(os.path.join(DOCS_DIR, "briefing", f"{date_str}.html"), "w", encoding="utf-8") as f:
        f.write(briefing_html)

    # ---- history.json 갱신 ----
    history_path = os.path.join(DATA_DIR, "history.json")
    history = load_json(history_path) if os.path.exists(history_path) else []
    history = [h for h in history if h["date"] != date_str]  # 같은 날 재실행 시 덮어쓰기
    cat_counts = {cat: len(v) for cat, v in grouped.items()}
    history.append({
        "date": date_str,
        "label": label,
        "highlight": build_highlight(len(company_articles), cat_counts),
    })
    history.sort(key=lambda h: h["date"], reverse=True)
    save_json(history_path, history)

    # ---- 홈 페이지 ----
    index_tpl = env.get_template("index.html")
    recent = history[1:6] if len(history) > 1 else []  # 오늘 제외, 최근 5개
    index_html = index_tpl.render(
        today={"date": date_str, "label": label, "short_label": short_label_for(date_str)},
        recent=recent,
    )
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # ---- 아카이브 페이지 ----
    archive_tpl = env.get_template("archive.html")
    archive_html = archive_tpl.render(history=history)
    with open(os.path.join(DOCS_DIR, "archive", "index.html"), "w", encoding="utf-8") as f:
        f.write(archive_html)

    print(f"사이트 생성 완료: {date_str} / 관심기업 {len(company_articles)}건 / "
          f"{ {k: len(v) for k, v in grouped.items()} }")


if __name__ == "__main__":
    main()
