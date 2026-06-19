"""동일 이슈 클러스터링 + 대표기사 선정."""
import re
from difflib import SequenceMatcher

import config
from core.logger import get_logger
from core.models import DedupedArticle, RawArticle

logger = get_logger()
_NON_WORD = re.compile(r"[^0-9a-zA-Z가-힣]+")


def _norm(title: str) -> str:
    return _NON_WORD.sub(" ", title).strip().lower()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _priority_rank(press: str) -> int:
    """우선 언론사일수록 낮은 값(우선). 가중치 용도."""
    for i, p in enumerate(config.PRIORITY_PRESS):
        if p in (press or ""):
            return i
    return len(config.PRIORITY_PRESS)


def _pick_representative(cluster: list[RawArticle]) -> RawArticle:
    """대표기사: ①우선언론사 ②최신성 ③원문접근 ④요약길이."""
    def key(a: RawArticle):
        return (
            _priority_rank(a.press or ""),                       # 작을수록 우선
            -(a.published_at.timestamp() if a.published_at else 0),  # 최신 우선
            0 if a.origin_url else 1,                            # 원문 있으면 우선
            -len(a.naver_summary or ""),                         # 요약 충실
        )
    return sorted(cluster, key=key)[0]


def deduplicate(articles: list[RawArticle]) -> list[DedupedArticle]:
    """제목 유사도 기반 그리디 클러스터링."""
    clusters: list[list[RawArticle]] = []
    for art in articles:
        placed = False
        for cl in clusters:
            if _similar(art.title, cl[0].title) >= config.TITLE_SIMILARITY_THRESHOLD:
                cl.append(art)
                placed = True
                break
        if not placed:
            clusters.append([art])

    result: list[DedupedArticle] = []
    for i, cl in enumerate(clusters):
        rep = _pick_representative(cl)
        result.append(DedupedArticle(
            **rep.model_dump(),
            cluster_id=f"c{i:04d}",
            duplicate_count=len(cl),
        ))
    logger.info("중복제거: %d건 → %d건", len(articles), len(result))
    return result
