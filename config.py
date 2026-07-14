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
    """환경변수/.env에서 키를 찾는다."""
    return os.getenv(name, default)


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
# '상태' 필드 타입: 노션에서 Status(상태) 타입이면 "status", Select(선택)면 "select"
NOTION_STATUS_TYPE = "status"         # "status" | "select"

# ── 카테고리 & 트렌드 검색어 ───────────────────────
# 일반 단어("여행") 대신 트렌드 분석 기사가 잡히도록 수식어를 결합한다.
# 카테고리당 핵심 2~3개로 압축해 무료 한도 안에서 동작하게 함.
CATEGORY_KEYWORDS = {
    "여가": ["여행 트렌드", "호텔 숙박 트렌드", "공연 전시 트렌드", "레저 트렌드"],
    "미디어콘텐츠": ["숏폼 트렌드", "OTT 트렌드", "크리에이터 이코노미", "팬덤 비즈니스"],
    "금융": ["간편결제 트렌드", "핀테크 트렌드", "포인트 멤버십 트렌드", "PLCC 트렌드"],
    "유통": ["이커머스 트렌드", "편의점 트렌드", "팝업스토어 트렌드", "리테일테크 트렌드"],
    "식품외식": ["외식 트렌드", "푸드테크 트렌드", "배달앱 트렌드", "간편식 트렌드"],
    "뷰티패션": ["뷰티 트렌드", "패션 플랫폼 트렌드", "화장품 소비 트렌드", "K뷰티 트렌드"],
    "모빌리티": ["모빌리티 트렌드", "전기차 충전 트렌드", "카셰어링 트렌드", "자율주행 서비스"],
    "세대담론": ["잘파세대 트렌드", "시니어 트렌드", "라이프스타일 소비 트렌드", "1인가구 트렌드"],
    "IT": ["생성형AI 서비스", "AI 에이전트 트렌드", "테크 서비스 트렌드", "온디바이스 AI"],
    "구독": ["구독 트렌드", "구독경제 트렌드", "멤버십 트렌드", "정기배송 트렌드"],
    "반려동물": ["반려동물 트렌드", "펫코노미 트렌드", "펫테크 트렌드", "반려동물 서비스"],
    "교육": ["교육 트렌드", "에듀테크 트렌드", "온라인 교육 트렌드", "AI 교육 서비스"],
    "웰니스": ["웰니스 트렌드", "헬스케어 트렌드", "멘탈케어 트렌드", "건강관리 트렌드"],
    "정치사회": ["정치사회 트렌드", "사회이슈 트렌드", "정책 트렌드", "여론 트렌드"],
}
CATEGORIES = list(CATEGORY_KEYWORDS.keys())

# ── 우선 언론사 (가중치, 절대필터 아님) ────────────
# 네이버 API 원문 링크에서는 언론사명이 아니라 도메인만 잡히는 경우가 많아
# 표시명과 도메인 힌트를 함께 매칭한다.
PRIORITY_PRESS = [
    "한국경제",
    "조선일보",
    "중앙일보",
    "동아일보",
    "경향신문",
    "한겨레",
    "머니투데이",
    "매일경제",
]
PRIORITY_PRESS_ALIASES = {
    "조선일보": ["조선일보", "chosun.com"],
    "중앙일보": ["중앙일보", "joongang.co.kr"],
    "동아일보": ["동아일보", "donga.com"],
    "경향신문": ["경향신문", "khan.co.kr"],
    "한겨레": ["한겨레", "hani.co.kr"],
    "머니투데이": ["머니투데이", "mt.co.kr"],
    "매일경제": ["매일경제", "mk.co.kr"],
    "한국경제": ["한국경제", "hankyung.com"],
}


def priority_press_rank(press: str) -> int:
    """우선 언론사일수록 낮은 값. 매칭 안 되면 목록 길이를 반환."""
    normalized = (press or "").lower()
    for i, name in enumerate(PRIORITY_PRESS):
        aliases = PRIORITY_PRESS_ALIASES.get(name, [name])
        if any(alias.lower() in normalized for alias in aliases):
            return i
    return len(PRIORITY_PRESS)


def priority_press_weight(press: str) -> int:
    """우선 언론사 가중치. 매칭 안 되면 0."""
    rank = priority_press_rank(press)
    return max(len(PRIORITY_PRESS) - rank, 0)

# ── 중복 판단 임계값 ───────────────────────────────
# 제목 문자열 유사도 또는 토큰 자카드 중 하나라도 이 값 이상이면 동일 이슈로 묶음.
# 0.55: 언론사만 다르고 표현이 살짝 바뀐 동일 사건까지 잡되, 다른 주제는 분리.
TITLE_SIMILARITY_THRESHOLD = 0.55
CONTENT_SIMILARITY_THRESHOLD = 0.42

# ── 트렌드 신호 (prefilter 가중치용) ────────────────
# "출시/론칭" 같은 단발성 새 소식보다, 반복·확산·소비행동 변화 신호에 더 큰 가중치를 둔다.
TREND_SIGNAL_KEYWORDS = [
    # 반복·확산·증가 신호
    "트렌드", "유행", "확산", "늘었다", "증가", "급증", "성장", "인기", "수요",
    "이용자", "사용자", "거래액", "판매량", "검색량", "데이터", "분석",
    "열풍", "주목", "부상", "뜬다", "대세", "신드롬", "바이럴",
    # 소비행동·라이프스타일 변화 신호
    "소비", "소비자", "고객", "경험", "취향", "선호", "라이프스타일",
    "구독", "멤버십", "커뮤니티", "팬덤", "크리에이터", "챌린지",
    "MZ", "잘파", "Z세대", "알파세대", "시니어", "1인가구",
    # 산업·서비스 변화 신호
    "플랫폼", "서비스", "전략", "협업", "제휴", "콜라보", "리테일테크",
    "푸드테크", "핀테크", "AI", "인공지능", "생성형", "에이전트", "자동화",
]
WEAK_NOVELTY_KEYWORDS = [
    "신규", "출시", "론칭", "첫", "최초", "처음", "도입", "오픈", "선보여",
]
# 기업 광고성(보도자료성) 기사 신호.
# 1차 필터에서 명백한 할인/이벤트성 기사를 줄이고, LLM/fallback에서도 재사용한다.
AD_STRONG_SIGNAL_KEYWORDS = [
    "할인 행사", "할인행사", "이벤트를 진행", "프로모션을 진행", "쿠폰 증정",
    "기념 이벤트", "특가", "사은품", "경품",
]
AD_SIGNAL_KEYWORDS = [
    "출시했다고 밝혔다", "선보인다고 밝혔다", "출시한다고 밝혔다", "선보인다고",
    "관계자는", "라고 밝혔다", "프로모션", "이벤트", "증정",
    "혜택을 제공", "참여 고객", "고객 대상", "판매한다", "오픈했다",
    "협업으로", "의뢰로",
]
AD_SIGNAL_THRESHOLD = 2   # 위 키워드가 이 개수 이상 겹치면 광고성으로 간주


def looks_like_promotional(text: str) -> bool:
    """기업 할인/이벤트/보도자료성 문구가 강하면 광고성 기사로 본다."""
    normalized = text or ""
    if any(kw in normalized for kw in AD_STRONG_SIGNAL_KEYWORDS):
        return True
    hits = sum(1 for kw in AD_SIGNAL_KEYWORDS if kw in normalized)
    return hits >= AD_SIGNAL_THRESHOLD

# 제목/요약에 등장하면 트렌드와 무관한 단발성 기사로 보고 감점
NOISE_KEYWORDS = [
    "부고", "인사", "동정", "별세", "장례", "주가", "코스피", "코스닥",
    "환율", "분양", "청약", "재건축", "사고", "화재", "사망", "체포", "구속",
    "기소", "판결", "선고", "날씨", "미세먼지", "경기결과", "스코어",
    "승리", "패배", "골", "득점",
]
