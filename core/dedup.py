"""동일 이슈 클러스터링 + 대표기사 선정."""
import re
from difflib import SequenceMatcher

import config
from core.logger import get_logger
from core.models import DedupedArticle, RawArticle

logger = get_logger()
_NON_WORD = re.compile(r"[^0-9a-zA-Z가-힣]+")
_BRACKET = re.compile(r"[\[\(<【［].*?[\]\)>】］]")   # [단독] [속보] (종합) 등
# 제목 끝에 흔히 붙는 언론사/형식 꼬리표
_TAIL = re.compile(r"(종합|속보|단독|포토|영상|인터뷰|일문일답|전문)\s*\d*$")


def _norm(title: str) -> str:
    t = title or ""
    t = _BRACKET.sub(" ", t)        # 머리 대괄호 제거
    t = _NON_WORD.sub(" ", t)
    t = _TAIL.sub(" ", t.strip())
    return t.strip().lower()


def _tokens(title: str) -> set[str]:
    """2글자 이상 토큰 집합(언론사만 다른 동일 사건 잡기용)."""
    return {w for w in _norm(title).split() if len(w) >= 2}


def _token_overlap(a: str, b: str) -> float:
    """자카드 유사도: 어순이 달라도 핵심 단어가 겹치면 동일 이슈로 본다."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _similar(a: str, b: str) -> float:
    """문자열 유사도와 토큰 자카드 중 큰 값(둘 중 하나만 높아도 동일 이슈)."""
    seq = SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    return max(seq, _token_overlap(a, b))


def _priority_rank(press: str) -> int:
    """우선 언론사일수록 낮은 값(우선). 가중치 용도."""
    return config.priority_press_rank(press)


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
    """제목 유사도 기반 그리디 클러스터링.

    개선점: 클러스터의 첫 기사뿐 아니라 '모든 구성원'과 비교한다.
    (A=B, B=C 인데 A≠C 인 연쇄 중복을 놓치지 않기 위함)
    """
    clusters: list[list[RawArticle]] = []
    for art in articles:
        placed = False
        for cl in clusters:
            if any(_similar(art.title, m.title) >= config.TITLE_SIMILARITY_THRESHOLD
                   for m in cl):
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
