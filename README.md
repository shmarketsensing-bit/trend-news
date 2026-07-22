# 트렌드 뉴스 수집 자동화 (로컬 MVP)

마켓센싱용 — 매일 08:00 네이버 뉴스 수집 → 중복제거 → 1차 필터(기본 15건) → 본문 추출 →
Gemini 분석/점수화 → 후보 10개 → Notion 업로드(상태=후보) → 노션에서 직접 검토.

## 구조

```
trend-news/
├── run_collect.py         # 08:00 배치 (수집~노션 업로드)
├── config.py              # 키워드/카테고리/임계값
├── core/
│   ├── collector.py       # 네이버 뉴스 검색 수집
│   ├── dedup.py           # 동일 이슈 중복 제거
│   ├── prefilter.py       # AI 분석 전 키워드 휴리스틱 1차 필터
│   ├── extractor.py       # 원문 본문 추출
│   ├── ai.py              # Gemini 배치 분석/점수화(캐시·쿼터 초과 시 규칙기반 폴백)
│   ├── ranker.py          # 최종 후보 선정(카테고리 분산·가중치 정렬)
│   ├── db.py              # SQLite 저장/캐시
│   ├── notion_client_wrap.py  # Notion 업로드/조회
│   ├── notion_learn.py    # (수동) "선정완료" 기사로 few-shot 예시 생성
│   ├── models.py
│   └── logger.py
├── prompts/analyze.txt
├── data/news.db           # SQLite (git 제외)
└── logs/                  # 실행 로그 (git 제외)
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

DB 속성 타입이 다르면 `config.py`에서 맞춰줘야 한다: **작성자**가 Text면
`NOTION_AUTHOR_TYPE = "rich_text"`(기본은 Multi-select용 `"multi_select"`), **URL**이 Text면
`NOTION_URL_TYPE = "rich_text"`, **상태**가 Select면 `NOTION_STATUS_TYPE = "select"`(기본은
Status 타입용 `"status"`). 안 맞으면 업로드 시 에러가 난다.

## 4. 실행

```bash
# 수동 1회 수집 → 노션에 "후보" 상태로 업로드
python run_collect.py
```

업로드된 기사는 노션 DB의 **상태** 컬럼(후보/선정/제외)을 직접 바꿔가며 검토한다.

**(선택) few-shot 학습 갱신**: 담당자가 노션에서 상태를 `config.NOTION_LEARNED_STATUS`
(기본 "선정완료")로 바꿔둔 기사들을 모아 `prompts/selected_examples.txt`를 다시 만들면, 이후
Gemini 분석 시 "실제로 우리가 고른 기사" 예시로 참고한다. `run_collect.py`가 자동으로 돌리지
않으므로, 선정 사례가 어느 정도 쌓였을 때(예: 주 1회) 수동 실행한다.

```bash
python -m core.notion_learn
```

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
- 중복 방지 3단: ① 같은 날 동일 원문은 SQLite `UNIQUE(origin_url, run_date)` ② 최근
  `RECENT_DAYS_DEDUP_WINDOW`일(기본 5일)간 노션에 올라간 제목과 유사하면 사전 제외 ③ 업로드
  직전에도 노션 URL 재조회로 이중 차단
- 실제 파이프라인 순서(`run_collect.py`): 수집(`collector`) → 중복제거(`dedup`) → 최근 노션
  이력과 유사 기사 제외 → 1차 필터(`prefilter`) → 본문 추출(`extractor`) → Gemini 분석
  (`ai`) → 후보 선정(`ranker`) → SQLite 저장 → 최근 이력 재확인 후 Notion 업로드
- 비용: **전 구성요소 무료**. Gemini는 기사 1건씩이 아니라 `GEMINI_BATCH_SIZE`(기본 5건)씩
  묶어서 배치 호출하고 SQLite에 캐시해 재실행 시 재호출하지 않음. 일일 쿼터를 넘기면 자동으로
  규칙 기반(rule-based) 폴백 점수화로 전환되어 실행 자체는 실패하지 않음
- 무료 티어 한도: Gemini Flash-Lite 약 1,000회/일·15회/분 · 네이버 25,000회/일 · Notion 무료
- **1차 필터(prefilter)**: 수집·중복제거 후 키워드 휴리스틱 점수로 상위 `PREFILTER_LIMIT`건
  (기본 15건)만 LLM 분석 대상으로 남김 → 무료 한도 안에서 안전
- `requirements.txt`는 `notion-client`를 `<2.6`으로 고정한다 — 2.6부터
  `databases.query()`가 제거되어 `core/notion_client_wrap.py`가 깨진다. 업그레이드하려면 해당
  호출부를 먼저 새 API로 바꿔야 함

## 7. 튜닝 포인트 (config.py)

| 값 | 의미 |
|----|------|
| `NAVER_DISPLAY` | 키워드당 검색 건수 |
| `COLLECT_WINDOW_HOURS` | 최근 N시간 내 기사만 수집(기본 24) |
| `RECENT_DAYS_DEDUP_WINDOW` | 최근 N일 노션 업로드 이력과 비교해 중복 제외(기본 5) |
| `PREFILTER_LIMIT` | LLM 분석 전 1차 필터로 남길 기사 수(기본 15, 무료 한도 보호) |
| `GEMINI_BATCH_SIZE` | Gemini 1회 호출에 묶어 보낼 기사 수(기본 5) |
| `CANDIDATE_COUNT` | 후보 수(기본 10) |
| `MAX_PER_CATEGORY` / `MIN_CATEGORIES` | 후보 내 카테고리당 상한 / 최소 걸쳐야 할 카테고리 수 |
| `TITLE_SIMILARITY_THRESHOLD` / `CONTENT_SIMILARITY_THRESHOLD` | 중복 판단 제목·본문 유사도(기본 0.55 / 0.42) |
| `GEMINI_MODEL` | 분석 모델(기본 `gemini-2.5-flash-lite`) |
| `GEMINI_MIN_INTERVAL` | 호출 간 최소 간격(초). 무료 RPM 보호 |
