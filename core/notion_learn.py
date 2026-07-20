"""Notion에서 '선정완료' 기사를 가져와 AI 프롬프트용 few-shot 예시를 생성.

독립 실행 스크립트 — 큐레이션이 쌓일 때마다(주 1회 등) 돌려
prompts/selected_examples.txt 를 최신 상태로 갱신한다.
core/ai.py가 모듈 로드 시 이 파일을 읽어 분석 프롬프트에 주입한다.

사용법: python -m core.notion_learn
"""
import config
from core import notion_client_wrap as notion
from core.logger import get_logger

logger = get_logger()

MAX_PER_CATEGORY = 4   # 카테고리당 최대 예시 수(프롬프트 토큰 보호)
MAX_TOTAL = 24
OUT_PATH = config.PROMPT_DIR / "selected_examples.txt"


def _format_example(row: dict) -> str:
    tags = ", ".join(row.get("hashtags") or [])
    note = (row.get("reason") or row.get("comment") or "").strip().replace("\n", " ")
    return (
        f"- 제목: {row.get('title', '')}\n"
        f"  카테고리: {row.get('category', '')}\n"
        f"  태그: {tags}\n"
        f"  선정 사유/코멘트: {note[:200]}"
    )


def build_examples_text(status: str | None = None) -> str:
    """노션에서 status(기본: config.NOTION_LEARNED_STATUS) 기사를 모아 few-shot 텍스트로 정리."""
    status = status or config.NOTION_LEARNED_STATUS
    rows = notion.fetch_candidates(status=status)
    if not rows:
        logger.warning("상태=%s 인 기사가 없습니다. 예시 없이 진행됩니다.", status)
        return ""

    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r.get("category") or "기타", []).append(r)

    picked: list[dict] = []
    for items in by_cat.values():
        picked.extend(items[:MAX_PER_CATEGORY])
    picked = picked[:MAX_TOTAL]

    logger.info("선정완료 예시 %d건 채택(전체 %d건 중, %d개 카테고리)",
                len(picked), len(rows), len(by_cat))
    return "\n".join(_format_example(r) for r in picked)


def main() -> int:
    if not (config.NOTION_API_KEY and config.NOTION_DATABASE_ID):
        logger.error("NOTION_API_KEY / NOTION_DATABASE_ID 누락(.env 확인). 중단.")
        return 1

    text = build_examples_text()
    if not text:
        logger.info("갱신할 예시 없음 — 기존 파일 유지.")
        return 0

    OUT_PATH.write_text(text, encoding="utf-8")
    logger.info("저장 완료: %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
