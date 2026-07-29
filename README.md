# 트렌드 뉴스 수집 자동화 (로컬 MVP)

마켓센싱용 — 매일 08:00 네이버 뉴스 수집 → 중복제거 → 1차 필터(기본 15건) → 본문 추출 →
Gemini 분석/점수화 → 후보 10개 → Notion 업로드(상태=후보) → 노션에서 직접 검토.

## 구조

```
trend-news/
├── .github/workflows/     # GitHub Actions 자동화(실제 운영 스케줄러)
│   ├── daily_news.yml         # 매일 08:07(KST) run_collect.py
│   └── update_examples.yml    # 매주 일요일 07:00(KST) core.notion_learn + git 커밋
├── run_collect.py         # 일일 배치 (수집~노션 업로드)
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
│   ├── notion_learn.py    # "선정완료" 기사로 few-shot 예시 생성(주 1회 별도 워크플로우가 자동 실행)
│   ├── kosis_publications.py  # KOSIS 온라인간행물 신규 발간 추적(자동 실행 안 함 — 수동 실행)
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

**few-shot 학습 갱신(자동, 주 1회)**: 담당자가 노션에서 상태를 `config.NOTION_LEARNED_STATUS`
(기본 "선정완료")로 바꿔둔 기사들을 `.github/workflows/update_examples.yml`이 **매주 일요일
07:00(KST)**에 모아 `prompts/selected_examples.txt`를 갱신하고 git에 커밋한다
(`core/notion_learn.py`). 이후 Gemini 분석이 "실제로 우리가 고른 기사" 예시를 참고하게 된다.

이 작업은 파일을 갱신하고 **git에 커밋까지 해야** 다음 배치에 반영되므로(GitHub Actions는
실행마다 새로 체크아웃하는 일회성 환경이라, 커밋 없이 파일만 써두면 실행 종료와 함께
사라진다) 매일 배치(`run_collect.py`)가 아니라 별도 워크플로우로 분리되어 있다. 갱신을
직접 실행해서 확인하고 싶으면 아래처럼 단독으로 돌릴 수도 있다(로컬 실행 시에는 별도로
git commit/push까지 직접 해야 반영된다).

```bash
python -m core.notion_learn
```

## 5. 자동화

**실제 운영 중인 자동화는 GitHub Actions다**(`.github/workflows/`) — 로컬 PC가 꺼져 있어도 돈다.

| 워크플로우 | 주기 | 하는 일 |
|---|---|---|
| `daily_news.yml` | 매일 08:07(KST) | `run_collect.py` — 뉴스 수집~노션 후보 업로드 |
| `update_examples.yml` | 매주 일요일 07:00(KST) | `core.notion_learn` — 선정완료 few-shot 예시 갱신 + git 커밋 |

두 워크플로우 모두 GitHub 저장소 Settings → Secrets에 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET`/
`GEMINI_API_KEY`/`NOTION_API_KEY`/`NOTION_DATABASE_ID`가 등록돼 있어야 하고(워크플로우별로
실제 쓰는 키만 주입됨), Actions 탭에서 `workflow_dispatch`로 수동 실행도 가능하다.

> `core/kosis_publications.py`(아래 5-1)는 별도 워크플로우 없이 **수동 실행 전용**이다(보류 중).

로컬 PC에서 직접 스케줄링하고 싶다면(권장하지 않음 — PC가 꺼져 있으면 안 돌아감):

**macOS / Linux** (`crontab -e`):
```
0 8 * * * cd /절대경로/trend-news && /절대경로/trend-news/.venv/bin/python run_collect.py >> logs/cron.log 2>&1
```

**Windows** (작업 스케줄러):
- 트리거: 매일 08:00
- 동작: 프로그램 `…\.venv\Scripts\python.exe`, 인수 `run_collect.py`, 시작 위치 `…\trend-news`

> 자동 실행 실패 시 → 해당 스크립트를 수동 재실행(`python run_collect.py` 등)하거나 Actions
> 탭에서 재실행(Re-run) 하면 된다.

## 5-1. KOSIS 온라인간행물 수집 (`core/kosis_publications.py`, 자동 실행 보류·수동 전용)

국가통계포털(KOSIS)의 "온라인간행물" 전체 카탈로그(94개 시리즈, 16개 테마)를 스캔해서,
`MIN_YEAR`(기본 2025) 이후 발간된 신규 항목만 노션에 "통계간행물" 카테고리로 업로드한다.
**자동 실행 워크플로우는 만들지 않기로 함(보류)** — 필요할 때 아래 명령으로 수동 실행한다.

- PDF 본문은 파싱하지 않는다 — 제목은 KOSIS가 제공하는 원래 발간본 이름(`korName`, 분기/계절/월
  등 세부 구분이 이미 포함돼 있음)을 그대로 쓰고, 시리즈명이 안 들어있으면 앞에 붙인다. "이런 신규
  통계가 나왔다"는 걸 담당자가 캐치하는 용도다(뉴스처럼 AI가 본문을 요약하지 않음).
  - PDF 본문 AI 요약은 검토해봤으나 보류: 실제 파일 다운로드 테스트 결과 100MB대 대용량 PDF가
    흔하고(GitHub Actions 15분 타임아웃 부담), 스캔본은 텍스트 추출이 0글자, 텍스트가 있어도
    비표준 폰트 인코딩으로 깨진 글자가 섞여 나와 요약 신뢰도를 담보하기 어려움. 필요해지면
    "용량 작은 것만 선별" 등으로 스코프를 좁혀 재검토.
- 시리즈마다 내부 구조가 달라서(연도당 PDF 1개인 단순한 시리즈도 있고, 연도→분기→통계표까지
  여러 단계로 쪼개진 시리즈도 있음), 일부 항목은 특정 파일로 바로 연결되는 링크 대신 KOSIS
  온라인간행물 목록 페이지로만 연결된다.
- **비공식(내부용) API를 쓴다** — `chapList.do`/`downSrvcFile.do` 모두 KOSIS가 공식 문서화한
  API가 아니라 웹페이지가 내부적으로 쓰는 엔드포인트라, 예고 없이 바뀌거나 막힐 수 있다.

단독 실행: `python -m core.kosis_publications`

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
