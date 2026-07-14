"""원문 본문 추출. 실패 시 네이버 요약문으로 fallback.

원문 페이지에 접속하는 김에 실제 제목(og:title)도 함께 가져온다.
네이버 뉴스 검색 API는 제목이 길면(특히 따옴표·대괄호가 섞인 헤드라인)
40~50자 선에서 잘라서 내려줄 때가 있어서, 원문 제목으로 보정한다.
"""
import requests
import trafilatura
from trafilatura.metadata import extract_metadata

from core.logger import get_logger
from core.models import DedupedArticle

logger = get_logger()
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TrendNewsBot/1.0)"}


def _fetch_page(url: str) -> tuple[str | None, str | None]:
    """(본문, 원문제목) 튜플. 실패 시 (None, None)."""
    if not url:
        return None, None
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return None, None

    body = trafilatura.extract(resp.text, include_comments=False,
                                include_tables=False, favor_recall=True)
    body = body.strip() if body and len(body.strip()) >= 200 else None

    title = None
    try:
        meta = extract_metadata(resp.text, default_url=url)
        if meta and meta.title:
            title = meta.title.strip()
    except Exception:
        title = None

    return body, title


def _better_title(naver_title: str, origin_title: str | None) -> str:
    """원문 제목이 있고 네이버 제목보다 더 온전해 보이면 그걸 쓴다.

    짧아지거나 사이트명만 남는 등 오추출 위험이 있으니, 원문 제목이
    네이버 제목을 '접두어로 포함'하면서 더 긴 경우만 안전하게 교체한다
    (= 정확히 잘린 지점 이후로 이어지는 케이스만 신뢰).
    """
    naver_title = (naver_title or "").strip()
    if not origin_title or len(origin_title) <= len(naver_title):
        return naver_title
    # 앞부분 20자 정도가 일치하면 같은 기사의 잘리지 않은 버전으로 간주
    prefix_len = min(20, len(naver_title))
    if naver_title[:prefix_len] and origin_title.startswith(naver_title[:prefix_len]):
        return origin_title
    return naver_title


def enrich_bodies(articles: list[DedupedArticle]) -> list[DedupedArticle]:
    ok = 0
    title_fixed = 0
    for a in articles:
        body, origin_title = _fetch_page(a.origin_url)
        if body:
            a.body = body
            a.body_source = "origin"
            ok += 1
        else:
            a.body = a.naver_summary
            a.body_source = "naver"

        fixed_title = _better_title(a.title, origin_title)
        if fixed_title != a.title:
            a.title = fixed_title
            title_fixed += 1

    logger.info("본문추출 성공 %d / %d (나머지 요약 fallback)", ok, len(articles))
    if title_fixed:
        logger.info("잘린 제목 원문 기준 보정 %d건", title_fixed)
    return articles