"""총점 + 카테고리 분산 규칙으로 후보 N개 선정."""
import config
from core.logger import get_logger
from core.models import AnalyzedArticle

logger = get_logger()


def select_candidates(articles: list[AnalyzedArticle]) -> list[AnalyzedArticle]:
    """
    1) 트렌드 가중 점수 내림차순 정렬 (트렌드성·신규성에 더 무게)
    2) 동일 카테고리 MAX_PER_CATEGORY 초과 방지하며 채움
    3) CANDIDATE_COUNT 미달 시 남은 기사로 보충
    4) 최소 MIN_CATEGORIES 카테고리 분산 보정
    """
    def weighted(a: AnalyzedArticle) -> float:
        s = a.scores
        # 총점(동일가중) 위에, 트렌드성·신규성을 추가 가산해 우선순위를 높임
        return a.total + s.trend * config.W_TREND + s.novelty * config.W_NOVELTY

    # 기업 광고성/보도자료성 기사는 후보에서 완전히 제외
    ads = [a for a in articles if a.is_ad]
    articles = [a for a in articles if not a.is_ad]
    if ads:
        logger.info("광고성 기사 제외: %d건 (%s)",
                    len(ads), ", ".join(a.title[:20] for a in ads[:5]))

    ranked = sorted(articles, key=weighted, reverse=True)
    selected: list[AnalyzedArticle] = []
    cat_count: dict[str, int] = {}

    # 1차: 카테고리 상한 지키며 채우기
    for a in ranked:
        if len(selected) >= config.CANDIDATE_COUNT:
            break
        if cat_count.get(a.category, 0) < config.MAX_PER_CATEGORY:
            selected.append(a)
            cat_count[a.category] = cat_count.get(a.category, 0) + 1

    # 2차: 미달 시 상한 무시하고 남은 상위 기사로 보충
    if len(selected) < config.CANDIDATE_COUNT:
        for a in ranked:
            if len(selected) >= config.CANDIDATE_COUNT:
                break
            if a not in selected:
                selected.append(a)

    # 3차: 카테고리 분산 부족 시 로그 경고(강제 교체는 MVP에서 생략)
    distinct = len({a.category for a in selected})
    if distinct < config.MIN_CATEGORIES:
        logger.warning("카테고리 분산 부족: %d종 (목표 %d)", distinct, config.MIN_CATEGORIES)

    logger.info("후보 선정 %d건 / 카테고리 %d종", len(selected), distinct)
    return selected
