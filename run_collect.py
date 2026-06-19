"""매일 08:00 OS 스케줄러가 호출하는 수집 배치 진입점.

흐름: 수집 → 중복제거 → 본문추출 → AI분석 → 후보선정 → SQLite 저장
"""
import sys
from datetime import datetime

import config
from core import ai, collector, db, dedup, extractor, prefilter, ranker
from core.logger import get_logger

logger = get_logger()


def run() -> int:
    run_date = datetime.now().strftime("%Y-%m-%d")
    logger.info("===== 수집 배치 시작 %s =====", run_date)

    # 키 점검
    if not (config.NAVER_CLIENT_ID and config.GEMINI_API_KEY):
        logger.error("API 키 누락(.env 확인). 중단.")
        return 1

    raw = collector.collect_all()
    if not raw:
        logger.error("수집 0건. 중단.")
        return 1

    deduped = dedup.deduplicate(raw)
    shortlisted = prefilter.prefilter(deduped)        # 무료 한도 보호: LLM 전 1차 컷
    enriched = extractor.enrich_bodies(shortlisted)   # 본문추출도 줄어든 대상만
    analyzed = ai.analyze_all(enriched)               # 배치 분석(+캐시/fallback)
    if not analyzed:
        # 분석 대상이 아예 없을 때만(수집은 됐으나 전부 기업로드 제외 등)
        logger.error("분석 대상 0건. 중단.")
        return 1

    candidates = ranker.select_candidates(analyzed)
    saved = db.save_candidates(candidates, run_date)
    s = ai.STATS
    logger.info(
        "저장 완료 %d건 (run_date=%s) | API호출 %d회·캐시 %d·AI성공 %d·실패 %d·fallback %d",
        saved, run_date, s["api_calls"], s["cache_hits"], s["ai_ok"],
        s["ai_fail"], s["fallback"],
    )
    logger.info("===== 수집 배치 종료 =====")
    return 0


if __name__ == "__main__":
    sys.exit(run())
