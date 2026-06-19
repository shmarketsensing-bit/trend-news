"""원문 본문 추출. 실패 시 네이버 요약문으로 fallback."""
import requests
import trafilatura

from core.logger import get_logger
from core.models import DedupedArticle

logger = get_logger()
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TrendNewsBot/1.0)"}


def _fetch_body(url: str) -> str | None:
    if not url:
        return None
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    text = trafilatura.extract(resp.text, include_comments=False,
                               include_tables=False, favor_recall=True)
    if text and len(text.strip()) >= 200:   # 너무 짧으면 추출 실패로 간주
        return text.strip()
    return None


def enrich_bodies(articles: list[DedupedArticle]) -> list[DedupedArticle]:
    ok = 0
    for a in articles:
        body = _fetch_body(a.origin_url)
        if body:
            a.body = body
            a.body_source = "origin"
            ok += 1
        else:
            a.body = a.naver_summary
            a.body_source = "naver"
    logger.info("본문추출 성공 %d / %d (나머지 요약 fallback)", ok, len(articles))
    return articles
