"""Notion에서 '선정완료' 기사를 가져와 AI 프롬프트용 few-shot 예시를 생성.

.github/workflows/update_examples.yml이 매주 일요일 07:00(KST)에 main()을 호출해
prompts/selected_examples.txt 를 갱신하고 git에 커밋한다(run_collect.py의 일일 배치와는
분리된 별도 워크플로우 — 파일을 갱신만 하고 커밋을 안 하면 GitHub Actions의 일회성
체크아웃 환경 특성상 실행 종료와 함께 그 갱신이 사라지기 때문).
core/ai.py는 모듈 로드(프로세스 시작) 시점에 이 파일을 한 번만 읽어 분석 프롬프트에
주입하므로, 갱신 내용은 다음 배치부터 반영된다.

단독 실행도 가능하다: python -m core.notion_learn (로컬 실행 시 git commit/push는 직접 해야 함)
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
