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

    # 노션에 '후보' 상태로 자동 업로드 (하이브리드: 출근 후 화면에서 큐레이션)
    if config.NOTION_API_KEY and config.NOTION_DATABASE_ID:
        from core import notion_client_wrap as notion
        from core.dedup import _similar

        # ── 업로드 대상: 그날 DB 전체가 아니라 '이번 실행의 후보'만 사용 ──
        # fetch_by_date는 같은 날 배치를 여러 번 돌리면 누적되므로 쓰지 않는다.
        # 방금 선정한 candidates를 점수순 상위 CANDIDATE_COUNT건으로 한 번 더 컷.
        run_rows = db.fetch_by_date(run_date)
        by_url = {r.get("origin_url"): r for r in run_rows}
        rows = []
        for c in candidates:
            r = by_url.get(c.origin_url)
            if r:                       # DB에 저장된 dict 형태(해시태그 파싱 등) 사용
                rows.append(r)
        # 안전장치: 어떤 이유로든 매칭 실패 시 점수순 상위로 폴백
        if not rows:
            rows = sorted(run_rows, key=lambda r: r.get("total") or 0, reverse=True)
        rows = rows[:config.CANDIDATE_COUNT]    # ★ 하드 캡: 항상 최대 N건만 업로드

        # 날짜 간 중복 제거: 최근 노션에 올라간 기사와 제목이 유사하면 업로드 제외
        # (어제 조선일보로 올라간 동일 사건이 오늘 중앙일보로 다시 잡히는 경우 차단)
        try:
            prev = notion.recent_titles(limit=100)
            kept = []
            for r in rows:
                t = r.get("title") or ""
                if any(_similar(t, pt) >= config.TITLE_SIMILARITY_THRESHOLD for pt in prev):
                    logger.info("날짜간 중복 제외: %s", t[:40])
                    continue
                kept.append(r)
            logger.info("날짜간 중복제거: %d건 → %d건", len(rows), len(kept))
            rows = kept
        except Exception as e:
            logger.warning("날짜간 중복체크 건너뜀: %s", e)

        logger.info("업로드 대상 최종 %d건 (CANDIDATE_COUNT=%d)",
                    len(rows), config.CANDIDATE_COUNT)
        res = notion.upload_many(rows, include_extended=config.NOTION_INCLUDE_EXTENDED,
                                 status="후보")
        logger.info("노션 후보 업로드 | 신규 %d·중복 %d·실패 %d",
                    res["uploaded"], res["duplicate"], res["failed"])
    else:
        logger.info("노션 키 없음 → 자동 업로드 생략(로컬 SQLite에만 저장)")

    logger.info("===== 수집 배치 종료 =====")
    return 0


if __name__ == "__main__":
    sys.exit(run())
