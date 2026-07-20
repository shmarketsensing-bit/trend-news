"""Gemini 배치 분석 + 캐시 + 일일한도 감지 + fallback.

무료 티어 보호 설계:
- 여러 기사(BATCH_SIZE)를 1회 호출로 묶어 분석 → 호출 수 대폭 절감
- 이미 분석한 URL은 SQLite 캐시에서 재사용(재분석 안 함)
- 일일 할당량 초과(GenerateRequestsPerDayPerProjectPerModel-FreeTier) 감지 시 즉시 중단
- 분석 실패/할당량 소진 시에도 네이버 제목·요약 기반 fallback 후보 생성
"""
import json
import re
import time

from google import genai
from google.genai import types
from google.genai.errors import APIError

import config
from core import db
from core.logger import get_logger, dump_failed
from core.models import AnalyzedArticle, DedupedArticle, Scores

logger = get_logger()
_client = None
_PROMPT = (config.PROMPT_DIR / "analyze_batch.txt").read_text(encoding="utf-8")
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
_last_call = 0.0


def _load_selected_examples() -> str:
    """core/notion_learn.py가 생성한 '선정완료' few-shot 사례 로드(없으면 빈 문자열)."""
    path = config.PROMPT_DIR / "selected_examples.txt"
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "(아직 선정 사례 없음)"


_SELECTED_EXAMPLES = _load_selected_examples()

# 호출 통계(로그용)
STATS = {"api_calls": 0, "cache_hits": 0, "ai_ok": 0, "ai_fail": 0, "fallback": 0}


class DailyQuotaExceeded(Exception):
    """일일 무료 할당량 초과. 즉시 중단 신호."""


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _throttle():
    global _last_call
    elapsed = time.time() - _last_call
    wait = config.GEMINI_MIN_INTERVAL - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def _is_daily_quota(err: Exception) -> bool:
    msg = str(err)
    return ("GenerateRequestsPerDayPerProjectPerModel-FreeTier" in msg
            or "PerDay" in msg)


def _build_batch_prompt(batch: list[DedupedArticle]) -> str:
    lines = []
    for i, a in enumerate(batch):
        body = (a.body or a.naver_summary or "")[:1500]   # 배치라 기사당 길이 제한
        lines.append(
            f'--- id: {i}\n제목: {a.title}\n언론사: {a.press or ""}\n'
            f'발행: {a.published_at.isoformat() if a.published_at else ""}\n본문: {body}'
        )
    block = "\n\n".join(lines)
    return (_PROMPT
            .replace("{category_list}", ", ".join(config.CATEGORIES))
            .replace("{selected_examples}", _SELECTED_EXAMPLES)
            .replace("{articles_block}", block))


def _parse_array(text: str) -> list | None:
    if not text:
        return None
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _call_batch(prompt: str) -> list | None:
    client = _get_client()
    _throttle()
    STATS["api_calls"] += 1
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
            max_output_tokens=config.GEMINI_BATCH_MAX_TOKENS,
        ),
    )
    return _parse_array(resp.text)


def _to_analyzed(a: DedupedArticle, data: dict) -> AnalyzedArticle | None:
    try:
        sc = data.get("scores", {})
        scores = Scores(
            trend=int(sc.get("trend", 0)), business=int(sc.get("business", 0)),
            novelty=int(sc.get("novelty", 0)), spread=int(sc.get("spread", 0)),
        )
        cat = data.get("category", "")
        if cat not in config.CATEGORIES:
            cat = a.category_hint or config.CATEGORIES[0]
        # comment가 배열이면 불릿 문자열로 정규화(줄바꿈 기준으로 노션에서 분리)
        raw_comment = data.get("comment", "")
        if isinstance(raw_comment, list):
            comment = "\n".join(
                f"- {str(x).strip().lstrip('-').strip()}"
                for x in raw_comment if str(x).strip()
            )
        else:
            comment = str(raw_comment)
        return AnalyzedArticle(
            **a.model_dump(),
            category=cat, suggested_category=data.get("suggested_category"),
            summary=data.get("summary", ""), comment=comment,
            implication=data.get("implication", ""),
            hashtags=data.get("hashtags", []) or [],
            scores=scores, total=scores.total, reason=data.get("reason", ""),
            is_ad=bool(data.get("is_ad", False)),
        )
    except (ValueError, TypeError) as e:
        logger.warning("배치 항목 파싱 오류: %s", e)
        return None


def _looks_like_ad(text: str) -> bool:
    """LLM 없이 쓰는 fallback 경로용 광고성 휴리스틱."""
    return config.looks_like_promotional(text)


def _fallback(a: DedupedArticle) -> AnalyzedArticle:
    """LLM 없이 네이버 제목·요약 기반 규칙 후보 생성."""
    STATS["fallback"] += 1
    summary = (a.naver_summary or a.title)[:300]
    # 간단 규칙 점수: 우선언론사/이슈성으로 trend·business 근사
    base = 3
    if config.priority_press_weight(a.press or ""):
        base = 4
    scores = Scores(trend=base, business=base, novelty=2, spread=2)
    # 광고성 판별은 네이버 짧은 요약(naver_summary)만으로는 놓치기 쉬우므로
    # 본문 추출이 됐다면(body_source=="origin") 본문까지 함께 검사한다.
    ad_check_text = f"{a.title} {summary}"
    if a.body_source == "origin" and a.body:
        ad_check_text += f" {a.body[:500]}"
    is_ad = _looks_like_ad(ad_check_text)
    return AnalyzedArticle(
        **a.model_dump(),
        category=a.category_hint or config.CATEGORIES[0],
        summary=summary,
        comment=summary,
        implication="(자동 생성) AI 분석 미적용 — 제목·요약 기반 후보입니다.",
        hashtags=[],
        scores=scores, total=scores.total,
        reason="AI 분석 미적용(할당량/실패) — 규칙 기반 fallback 후보",
        is_ad=is_ad,
    )


def analyze_all(articles: list[DedupedArticle]) -> list[AnalyzedArticle]:
    """배치 분석. 캐시 우선, 할당량 초과 시 남은 기사는 fallback."""
    results: list[AnalyzedArticle] = []

    # 1) 캐시 적용
    urls = [a.origin_url for a in articles if a.origin_url]
    cached = db.get_cached_analyses(urls)
    todo: list[DedupedArticle] = []
    for a in articles:
        c = cached.get(a.origin_url)
        if c:
            merged = _to_analyzed(a, c)
            if merged:
                results.append(merged)
                STATS["cache_hits"] += 1
                continue
        todo.append(a)

    # 2) 배치 분석
    quota_hit = False
    for start in range(0, len(todo), config.GEMINI_BATCH_SIZE):
        batch = todo[start:start + config.GEMINI_BATCH_SIZE]
        if quota_hit:
            results.extend(_fallback(a) for a in batch)
            continue

        prompt = _build_batch_prompt(batch)
        data = None
        for attempt in range(config.GEMINI_MAX_RETRIES):
            try:
                data = _call_batch(prompt)
                break
            except APIError as e:
                if _is_daily_quota(e):
                    logger.error("일일 할당량 초과 감지 → 이후 기사는 fallback 처리")
                    quota_hit = True
                    break
                wait = config.GEMINI_RETRY_BACKOFF * (attempt + 1)
                logger.warning("Gemini 오류(%d/%d): %s → %ds 대기",
                               attempt + 1, config.GEMINI_MAX_RETRIES, e, wait)
                time.sleep(wait)
            except Exception as e:
                logger.warning("Gemini 예외(%d): %s", attempt + 1, e)

        if data is None:
            # 이 배치 실패 → fallback
            for a in batch:
                STATS["ai_fail"] += 1
                results.append(_fallback(a))
            dump_failed("ai_batch", {"count": len(batch)})
            continue

        # id 매핑
        by_id = {int(d.get("id", -1)): d for d in data if isinstance(d, dict)}
        for i, a in enumerate(batch):
            d = by_id.get(i)
            merged = _to_analyzed(a, d) if d else None
            if merged:
                results.append(merged)
                STATS["ai_ok"] += 1
                # 캐시 저장
                db.save_analysis_cache(a.origin_url, d)
            else:
                STATS["ai_fail"] += 1
                results.append(_fallback(a))

    logger.info(
        "분석 통계 | API호출:%d 캐시:%d 성공:%d 실패:%d fallback:%d",
        STATS["api_calls"], STATS["cache_hits"], STATS["ai_ok"],
        STATS["ai_fail"], STATS["fallback"],
    )
    return results