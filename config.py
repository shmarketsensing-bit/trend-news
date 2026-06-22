"""설정, 카테고리/키워드, 우선 언론사 등 상수 관리."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── 경로 ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FAILED_DIR = DATA_DIR / "failed"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "news.db"
PROMPT_DIR = BASE_DIR / "prompts"
for d in (DATA_DIR, FAILED_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _secret(name: str, default: str = "") -> str:
    """키를 두 곳에서 찾는다: ①환경변수/.env ②Streamlit Cloud Secrets.

    로컬에서는 .env(os.environ)를, Streamlit Cloud 배포에서는
    st.secrets를 읽는다. 둘 중 먼저 발견되는 값을 사용.
    """
    val = os.getenv(name, "")
    if val:
        return val
    try:
        import streamlit as st  # 배포 환경에만 의미 있음
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


# ── API 키 (.env 또는 Streamlit Secrets) ───────────
NAVER_CLIENT_ID = _secret("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = _secret("NAVER_CLIENT_SECRET")
GEMINI_API_KEY = _secret("GEMINI_API_KEY")
NOTION_API_KEY = _secret("NOTION_API_KEY")
NOTION_DATABASE_ID = _secret("NOTION_DATABASE_ID")

# ── 모델 (Google AI Studio 무료 티어) ──────────────
# flash-lite: 무료 한도가 가장 넉넉(분당 15회·하루 1,000회 수준), 분류/요약에 충분
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_MAX_TOKENS = 1500
# 무료 RPM 보호용 호출 간 최소 간격(초). flash-lite 15 RPM 기준 4.5초면 안전.
GEMINI_MIN_INTERVAL = 4.5
GEMINI_MAX_RETRIES = 3          # 429 등 일시 오류 재시도 횟수
GEMINI_RETRY_BACKOFF = 20       # 재시도 대기(초) × 시도횟수
# 배치 분석: 여러 기사를 1회 호출로 묶음 → 무료 한도 보호
GEMINI_BATCH_SIZE = 5          # 1회 호출당 기사 수 (5~10 권장)
GEMINI_BATCH_MAX_TOKENS = 4000  # 배치 응답은 길어지므로 토큰 상향

# ── 수집 파라미터 ──────────────────────────────────
COLLECT_WINDOW_HOURS = 24       # 최근 24시간 내 기사만(어제 업로드분과 겹침 방지)
NAVER_DISPLAY = 5              # 키워드당 네이버 검색 건수(무료 한도 보호 위해 축소)
PREFILTER_LIMIT = 15           # AI 분석 대상 최대(10~15). 배치 3회 이내로 제한
CANDIDATE_COUNT = 10           # 최종 후보 기사 수
MAX_PER_CATEGORY = 4           # 후보 내 동일 카테고리 최대
MIN_CATEGORIES = 3             # 후보가 걸쳐야 할 최소 카테고리 수
# 최종 후보 정렬 가중치(총점에 추가로 더해짐) — 트렌드성·신규성 우선
W_TREND = 1.5                  # 트렌드성 점수 추가 가중
W_NOVELTY = 1.0                # 신규성 점수 추가 가중
DEFAULT_AUTHOR = "Claude"

# ── Notion 필드 매핑 ───────────────────────────────
# 코드 키 → 실제 노션 DB의 속성(컬럼) 이름.
# 노션 DB 컬럼명을 바꿨다면 여기 오른쪽 값만 고치면 된다.
NOTION_FIELDS = {
    "title":    "제목",          # Title 타입
    "category": "카테고리",       # Select 타입
    "comment":  "요약",          # Text(rich_text) 타입
    "url":      "URL",           # URL 타입
    "hashtags": "태그",          # Multi-select 타입
    "author":   "작성자",         # ※ 이 DB에선 Multi-select 타입
    # 확장(선택) — DB에 없으면 자동으로 건너뜀
    "press":        "언론사",
    "published_at": "발행일시",
    "collected_at": "스크랩 날짜",   # Date 타입 (필수 취급)
    "total":        "트렌드 점수",
    "reason":       "추천 사유",
    "memo":         "담당자 메모",
    "upload_status": "상태",        # Select: 후보 | 선정 | 제외
}
# '작성자' 필드 타입: 이 DB는 multi_select 이므로 그렇게 보냄.
# (만약 작성자를 Text로 만들었다면 "rich_text"로 바꾸세요)
NOTION_AUTHOR_TYPE = "multi_select"   # "multi_select" | "rich_text"
# URL 필드 타입: 이 DB가 URL 타입이면 "url", Text면 "rich_text"
NOTION_URL_TYPE = "url"               # "url" | "rich_text"
# Actions 자동 업로드 시 확장필드(언론사·점수 등) 포함 여부.
# DB에 확장 컬럼이 없으면 False로 둔다(필수 필드만 올림).
NOTION_INCLUDE_EXTENDED = False

# ── 카테고리 & 트렌드 검색어 ───────────────────────
# 일반 단어("여행") 대신 트렌드 분석 기사가 잡히도록 수식어를 결합한다.
# 카테고리당 핵심 2~3개로 압축해 무료 한도 안에서 동작하게 함.
CATEGORY_KEYWORDS = {
    "여가": ["여행 트렌드", "2026 여행", "팝업스토어 트렌드"],
    "미디어콘텐츠": ["콘텐츠 트렌드", "숏폼 트렌드", "OTT 트렌드"],
    "금융": ["카드 트렌드", "간편결제 트렌드", "소비 트렌드"],
    "유통": ["유통 트렌드", "이커머스 트렌드", "편의점 트렌드"],
    "식품외식": ["외식 트렌드", "푸드 트렌드", "배달 트렌드"],
    "뷰티패션": ["뷰티 트렌드", "패션 트렌드", "화장품 트렌드"],
    "모빌리티": ["모빌리티 트렌드", "전기차 트렌드"],
    "라이프스타일": ["라이프스타일 트렌드", "소비자 트렌드", "MZ 트렌드"],
    "IT": ["AI 트렌드", "생성형AI 서비스", "테크 트렌드"],
}
CATEGORIES = list(CATEGORY_KEYWORDS.keys())

# ── 우선 언론사 (가중치, 절대필터 아님) ────────────
PRIORITY_PRESS = ["조선일보", "중앙일보", "동아일보", "한국경제", "매일경제", "연합뉴스"]

# ── 중복 판단 임계값 ───────────────────────────────
TITLE_SIMILARITY_THRESHOLD = 0.70  # 제목 70% 이상 유사 → 동일 이슈 후보

# ── 트렌드 신호 (prefilter 가중치용) ────────────────
# 제목/요약에 등장하면 트렌드성이 높다고 보고 가산점
TREND_SIGNAL_KEYWORDS = [
    # 변화·신규성 신호
    "신규", "출시", "론칭", "첫", "최초", "처음", "도입", "확대", "급증", "돌풍",
    "열풍", "인기", "化", "뜬다", "주목", "부상", "트렌드", "유행", "новый",
    "MZ", "잘파", "Z세대", "알파세대", "신드롬", "챌린지", "바이럴",
    # 비즈니스·소비 신호
    "소비", "결제", "구독", "멤버십", "포인트", "혜택", "할인", "리워드",
    "플랫폼", "서비스", "전략", "협업", "제휴", "콜라보", "PLCC", "데이터",
    # 기술 신호
    "AI", "인공지능", "생성형", "에이전트", "자동화", "디지털", "앱",
]
# 제목/요약에 등장하면 트렌드와 무관한 단발성 기사로 보고 감점
NOISE_KEYWORDS = [
    "부고", "인사", "동정", "별세", "장례", "주가", "코스피", "코스닥",
    "환율", "분양", "청약", "재건축", "사고", "화재", "사망", "체포", "구속",
    "기소", "판결", "선고", "날씨", "미세먼지", "경기결과", "스코어",
    "승리", "패배", "골", "득점",
]
