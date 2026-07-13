# 트렌드 뉴스 수집 자동화 (로컬 MVP)

마켓센싱용 — 매일 08:00 네이버 뉴스 수집 → 중복제거 → 1차 필터(60건) → Gemini 분석/점수화 → 후보 10개 → Notion 업로드(상태=후보) → 노션에서 직접 검토.

## 구조

```
trend-news/
├── run_collect.py    # 08:00 배치 (수집~노션 업로드)
├── config.py         # 키워드/카테고리/임계값
├── core/             # collector·dedup·extractor·ai·ranker·db·notion·models·logger
├── prompts/analyze.txt
├── data/news.db      # SQLite (git 제외)
└── logs/             # 실행 로그 (git 제외)
```

## 1. 설치

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # 키 입력
```

## 2. 키 발급

| 키 | 발급처 |
|----|--------|
| NAVER_CLIENT_ID/SECRET | https://developers.naver.com (검색 API 신청) |
| GEMINI_API_KEY | https://aistudio.google.com/apikey (결제연결 불필요·무료) |
| NOTION_API_KEY | https://www.notion.so/my-integrations |
| NOTION_DATABASE_ID | 대상 DB URL의 32자리 ID. **통합(integration)을 해당 DB에 연결**해야 함 |

## 3. Notion DB 필드

**필수**: 뉴스타이틀(Title), 카테고리(Select), 주요내용 및 코멘트 요약(Text),
관련 뉴스 URL(URL), 해시태그(Multi-select), 작성자(Text)

**확장(선택)**: 언론사·발행일시·수집일시·트렌드 점수·추천 사유·담당자 메모·업로드 상태
→ 확장 필드를 안 만들었다면 `config.py`의 `NOTION_INCLUDE_EXTENDED = False`로 둔다.

## 4. 실행

```bash
# 수동 1회 수집 → 노션에 "후보" 상태로 업로드
python run_collect.py
```

업로드된 기사는 노션 DB의 **상태** 컬럼(후보/선정/제외)을 직접 바꿔가며 검토한다.

## 5. 매일 08:00 자동화

**macOS / Linux** (`crontab -e`):
```
0 8 * * * cd /절대경로/trend-news && /절대경로/trend-news/.venv/bin/python run_collect.py >> logs/cron.log 2>&1
```

**Windows** (작업 스케줄러):
- 트리거: 매일 08:00
- 동작: 프로그램 `…\.venv\Scripts\python.exe`, 인수 `run_collect.py`, 시작 위치 `…\trend-news`

> 08:00 실행 실패 시 → `python run_collect.py`로 수동 재실행.

## 6. 운영 메모

- 실행 로그: `logs/collect_YYYYMMDD.log`
- 실패 기사 덤프: `data/failed/`
- 중복 방지: 같은 날 동일 원문은 SQLite `UNIQUE(origin_url, run_date)`, Notion은 업로드 전 URL 조회로 이중 차단
- 비용: **전 구성요소 무료**. 기사 1건당 Gemini 1회 호출(무료 티어). 후보 산정 전 중복제거로 호출 수를 줄임
- 무료 티어 한도: Gemini Flash-Lite 약 1,000회/일·15회/분 · 네이버 25,000회/일 · Notion 무료
- **1차 필터(prefilter)**: 수집·중복제거 후 키워드 휴리스틱으로 60건만 LLM 분석 → 무료 한도 안에서 안전. config.py의 `PREFILTER_LIMIT`로 조절

## 7. 튜닝 포인트 (config.py)

| 값 | 의미 |
|----|------|
| `NAVER_DISPLAY` | 키워드당 검색 건수 |
| `PREFILTER_LIMIT` | LLM 분석 전 1차 필터로 남길 기사 수(무료 한도 보호) |
| `CANDIDATE_COUNT` | 후보 수(기본 10) |
| `MAX_PER_CATEGORY` | 후보 내 동일 카테고리 상한 |
| `TITLE_SIMILARITY_THRESHOLD` | 중복 판단 제목 유사도(0.70) |
| `GEMINI_MODEL` | 분석 모델(무료: gemini-2.5-flash / 더 가벼운: -flash-lite) |
| `GEMINI_MIN_INTERVAL` | 호출 간 최소 간격(초). 무료 RPM 보호 |
