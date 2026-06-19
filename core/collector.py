"""네이버 뉴스 검색 API 수집 (최근 24시간 필터)."""
import html
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

import config
from core.logger import get_logger
from core.models import RawArticle

logger = get_logger()
NAVER_URL = "https://openapi.naver.com/v1/search/news.json"
KST = timezone(timedelta(hours=9))
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _parse_pubdate(raw: str):
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


def _guess_press(origin_url: str) -> str:
    """원문 URL 도메인에서 언론사 추정(간이)."""
    m = re.search(r"https?://(?:www\.)?([^/]+)", origin_url or "")
    return m.group(1) if m else ""


def _search_keyword(keyword: str, category: str, cutoff: datetime) -> list[RawArticle]:
    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": config.NAVER_DISPLAY, "sort": "date"}
    try:
        resp = requests.get(NAVER_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("네이버 API 실패 [%s]: %s", keyword, e)
        return []

    items = resp.json().get("items", [])
    out: list[RawArticle] = []
    for it in items:
        pub = _parse_pubdate(it.get("pubDate", ""))
        if pub and pub < cutoff:           # 24시간 초과 → 제외
            continue
        origin = it.get("originallink") or it.get("link", "")
        out.append(RawArticle(
            title=_clean(it.get("title", "")),
            press=_guess_press(origin),
            published_at=pub,
            naver_url=it.get("link", ""),
            origin_url=origin,
            naver_summary=_clean(it.get("description", "")),
            keyword=keyword,
            category_hint=category,
        ))
    return out


def collect_all() -> list[RawArticle]:
    """전체 카테고리/키워드 순회 수집."""
    cutoff = datetime.now(KST) - timedelta(hours=config.COLLECT_WINDOW_HOURS)
    collected: list[RawArticle] = []
    for category, keywords in config.CATEGORY_KEYWORDS.items():
        for kw in keywords:
            arts = _search_keyword(kw, category, cutoff)
            collected.extend(arts)
            logger.info("수집 [%s/%s] %d건", category, kw, len(arts))
            time.sleep(0.1)   # 호출 간 간격
    logger.info("수집 합계 %d건", len(collected))
    return collected
