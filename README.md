# 오늘의 마케팅 브리핑 (v2)

마케팅·브랜드·콘텐츠 뉴스 + **관심기업** 뉴스를 매일 자동으로 모아주는 정적 사이트.
AI 요약 없이 **규칙 기반**으로 동작하고, **최근 24시간 이내 발행된 기사만** 수록합니다.
매일 GitHub Actions가 실행되어 자동으로 새 브리핑을 만들고 GitHub Pages에 배포합니다.

## 폴더 구조

```
config/
  companies.json    # 관심기업 목록 (기업명: [별칭 리스트])
  categories.json    # 카테고리별 검색어/색상
scripts/
  fetch_news.py      # 구글 뉴스 RSS에서 최근 24시간 기사 수집
  summarize.py        # 규칙 기반 요약 생성 (무슨 내용/왜 중요/조언)
  build_site.py        # docs/ 에 정적 HTML 사이트 생성
templates/            # Jinja2 HTML 템플릿 (디자인 수정은 여기서)
static/style.css       # 전체 스타일 (색상, 폰트 등)
data/                 # 수집된 기사 데이터 + 발행 이력 (자동 생성/커밋됨)
docs/                  # 최종 배포되는 정적 사이트 (GitHub Pages 소스)
.github/workflows/    # 매일 자동 실행 워크플로우
```

## 1. 로컬에서 한 번 실행해보기

```bash
pip install -r requirements.txt
cd scripts
python fetch_news.py     # data/raw_articles.json 생성
python summarize.py       # data/articles_enriched.json 생성
python build_site.py       # docs/ 사이트 생성
```

생성된 `docs/index.html`을 브라우저로 열어서 확인할 수 있습니다.

## 2. 관심기업 수정하기

`config/companies.json`을 열어 원하는 기업과 별칭(약칭·영문명 등)을 추가하세요.
별칭이 많을수록 기사 매칭이 더 잘 됩니다.

```json
{
  "지원하는 회사": ["정식명칭", "영문명", "약칭"]
}
```

## 3. 카테고리 / 검색어 수정하기

`config/categories.json`에서 카테고리 이름, 검색어(queries), 색상을 바꿀 수 있습니다.

## 4. GitHub에 올리고 자동화 켜기

1. 이 폴더 전체를 새 GitHub 저장소에 push
2. 저장소 **Settings → Pages** 에서 Source를 `Deploy from a branch`, 브랜치는 `main`, 폴더는 `/docs`로 설정
3. **Settings → Actions → General → Workflow permissions** 에서 `Read and write permissions` 선택 (자동 커밋을 위해 필요)
4. **Actions** 탭에서 `Daily Marketing Briefing` 워크플로우를 한 번 수동 실행(`Run workflow`)해서 첫 브리핑 생성
5. 이후 매일 한국시간 08:00에 자동 실행됩니다 (cron 시간은 `.github/workflows/daily-briefing.yml`에서 수정 가능)

## 5. "최근 24시간" 기준 조정

`scripts/common.py`의 `WINDOW_HOURS` (기본 24)를 바꾸면 기간을 조절할 수 있습니다.
환경변수 `BRIEFING_WINDOW_HOURS`로도 덮어쓸 수 있습니다.

## 왜 이전 버전과 다른가요

- 이전 버전: 카테고리 뉴스만 큐레이션, 기간 제한 없이 매일 최신 기사를 계속 나열
- 이번 버전: **관심기업 섹션 추가** + 기사가 **최근 24시간 이내 발행된 것만** 표시되도록 필터링,
  기사마다 "무슨 내용인가요 / 왜 중요한가요 / 참고하면 좋은 점" 3단 요약 카드로 디자인 개편
