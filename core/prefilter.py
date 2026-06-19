"""AI 분석 전 1차 필터(prefilter).

Gemini 무료 한도를 아끼기 위해, 점수화(LLM) 전에 가벼운 휴리스틱으로
분석 대상을 PREFILTER_LIMIT 건으로 줄인다. LLM 호출이 전혀 없다.

휴리스틱 점수:
- 우선 언론사 가중치
- 본문 추출 성공(origin) 가산
- 중복 클러스터 크기(여러 매체가 보도 = 이슈성) 가산
- 제목/요약 길이(내용 충실도) 소폭 가산
- 카테고리 분산: 한 카테고리가 과점하지 않도록 상한 적용
"""
import config
from core.logger import get_logger
from core.models import DedupedArticle

logger = get_logger()


def _heuristic_score(a: DedupedArticle) -> float:
    score = 0.0
    text = f"{a.title} {a.naver_summary}"

    # 우선 언론사 (앞순위일수록 높게)
    for i, p in enumerate(config.PRIORITY_PRESS):
        if p in (a.press or ""):
            score += (len(config.PRIORITY_PRESS) - i) * 2
            break
    # 본문 추출 성공
    if a.body_source == "origin":
        score += 5
    # 이슈성(여러 매체 보도)
    score += min(a.duplicate_count, 5) * 2
    # 내용 충실도
    score += min(len(a.naver_summary or ""), 300) / 100.0

    # 트렌드 신호: 등장 키워드마다 가산(상한 있음)
    trend_hits = sum(1 for kw in config.TREND_SIGNAL_KEYWORDS if kw in text)
    score += min(trend_hits, 6) * 3        # 트렌드성을 가장 크게 반영

    # 노이즈 신호: 단발성·비트렌드 기사 감점
    noise_hits = sum(1 for kw in config.NOISE_KEYWORDS if kw in text)
    score -= noise_hits * 4

    return score


def prefilter(articles: list[DedupedArticle]) -> list[DedupedArticle]:
    # 이미 노션 업로드 완료된 기사는 후보에서 제외(어제 업로드분 재등장 방지)
    try:
        from core import db
        done = db.uploaded_urls()
        if done:
            before = len(articles)
            articles = [a for a in articles if a.origin_url not in done]
            logger.info("기업로드 URL 제외: %d건 제거", before - len(articles))
    except Exception as e:
        logger.warning("기업로드 URL 조회 실패(무시): %s", e)

    limit = config.PREFILTER_LIMIT
    if len(articles) <= limit:
        return articles

    ranked = sorted(articles, key=_heuristic_score, reverse=True)

    # 카테고리 과점 방지: 카테고리당 상한을 두고 채움
    per_cat_cap = max(limit // max(len(config.CATEGORIES), 1) + 2, 4)
    picked: list[DedupedArticle] = []
    cat_count: dict[str, int] = {}
    for a in ranked:
        if len(picked) >= limit:
            break
        c = a.category_hint or ""
        if cat_count.get(c, 0) < per_cat_cap:
            picked.append(a)
            cat_count[c] = cat_count.get(c, 0) + 1

    # 상한 때문에 미달하면 남은 상위로 보충
    if len(picked) < limit:
        for a in ranked:
            if len(picked) >= limit:
                break
            if a not in picked:
                picked.append(a)

    logger.info("1차 필터: %d건 → %d건 (LLM 분석 대상)", len(articles), len(picked))
    return picked
