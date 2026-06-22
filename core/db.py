"""SQLite 저장소: 스키마, 저장, 조회, 상태 갱신."""
import json
import sqlite3
from datetime import datetime
from typing import Optional

import config
from core.models import AnalyzedArticle
from core.logger import get_logger

logger = get_logger()

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT,
    cluster_id TEXT,
    duplicate_count INTEGER DEFAULT 1,
    category TEXT,
    suggested_category TEXT,
    title TEXT,
    press TEXT,
    published_at TEXT,
    collected_at TEXT,
    naver_url TEXT,
    origin_url TEXT,
    body_source TEXT,
    summary TEXT,
    comment TEXT,
    implication TEXT,
    hashtags TEXT,
    score_trend INTEGER,
    score_business INTEGER,
    score_novelty INTEGER,
    score_spread INTEGER,
    total INTEGER,
    reason TEXT,
    status TEXT DEFAULT '후보',
    memo TEXT DEFAULT '',
    author TEXT DEFAULT 'Claude',
    UNIQUE(origin_url, run_date)
);

CREATE TABLE IF NOT EXISTS analysis_cache (
    origin_url TEXT PRIMARY KEY,
    payload TEXT,           -- AnalyzedArticle 분석결과 JSON
    cached_at TEXT
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def clear_run_date(run_date: str) -> int:
    """해당 run_date의 기존 후보 행을 삭제. 같은 날 재실행 시 누적 방지.

    (노션에 이미 올라간 건은 노션에서 큐레이션되므로 로컬 DB는 매 실행 새로 써도 안전)
    반환: 삭제된 행 수.
    """
    init_db()
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM articles WHERE run_date=?", (run_date,))
        conn.commit()
        return cur.rowcount


def save_candidates(articles: list[AnalyzedArticle], run_date: str,
                    replace: bool = True) -> int:
    """후보 기사 일괄 저장. UNIQUE 충돌(중복 원문)은 무시. 저장 건수 반환.

    replace=True면 같은 run_date의 기존 행을 먼저 비운다(재실행 누적 방지).
    """
    init_db()
    if replace:
        deleted = clear_run_date(run_date)
        if deleted:
            logger.info("재실행 감지: %s 기존 %d건 삭제 후 재저장", run_date, deleted)
    saved = 0
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        for a in articles:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO articles
                    (run_date, cluster_id, duplicate_count, category, suggested_category,
                     title, press, published_at, collected_at, naver_url, origin_url,
                     body_source, summary, comment, implication, hashtags,
                     score_trend, score_business, score_novelty, score_spread,
                     total, reason, status, author)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        run_date, a.cluster_id, a.duplicate_count, a.category,
                        a.suggested_category, a.title, a.press,
                        a.published_at.isoformat() if a.published_at else None,
                        now, a.naver_url, a.origin_url, a.body_source,
                        a.summary, a.comment, a.implication,
                        json.dumps(a.hashtags, ensure_ascii=False),
                        a.scores.trend, a.scores.business, a.scores.novelty,
                        a.scores.spread, a.total, a.reason,
                        "후보", config.DEFAULT_AUTHOR,
                    ),
                )
                saved += conn.total_changes and 1 or 0
            except sqlite3.Error:
                continue
        conn.commit()
    return saved


def list_run_dates() -> list[str]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT run_date FROM articles ORDER BY run_date DESC"
        ).fetchall()
    return [r["run_date"] for r in rows if r["run_date"]]


def fetch_by_date(run_date: str) -> list[dict]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles WHERE run_date=? ORDER BY total DESC",
            (run_date,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["hashtags"] = json.loads(d.get("hashtags") or "[]")
        except json.JSONDecodeError:
            d["hashtags"] = []
        out.append(d)
    return out


def update_status(article_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE articles SET status=? WHERE id=?", (status, article_id))
        conn.commit()


def update_memo(article_id: int, memo: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE articles SET memo=? WHERE id=?", (memo, article_id))
        conn.commit()


def fetch_selected(run_date: str) -> list[dict]:
    """업로드 대상(status='선정')."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles WHERE run_date=? AND status='선정'",
            (run_date,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["hashtags"] = json.loads(d.get("hashtags") or "[]")
        except json.JSONDecodeError:
            d["hashtags"] = []
        out.append(d)
    return out

# ── 분석 캐시 (이미 분석한 URL 재분석 방지) ──────────
def get_cached_analyses(urls: list[str]) -> dict[str, dict]:
    """주어진 URL들 중 캐시에 있는 분석결과를 {url: payload_dict}로 반환."""
    if not urls:
        return {}
    init_db()
    out: dict[str, dict] = {}
    with get_conn() as conn:
        qmarks = ",".join("?" * len(urls))
        rows = conn.execute(
            f"SELECT origin_url, payload FROM analysis_cache WHERE origin_url IN ({qmarks})",
            urls,
        ).fetchall()
    for r in rows:
        try:
            out[r["origin_url"]] = json.loads(r["payload"])
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def save_analysis_cache(url: str, payload: dict) -> None:
    """분석결과를 캐시에 저장(upsert)."""
    if not url:
        return
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analysis_cache (origin_url, payload, cached_at) VALUES (?,?,?)",
            (url, json.dumps(payload, ensure_ascii=False, default=str), now),
        )
        conn.commit()


def uploaded_urls() -> set[str]:
    """이미 노션 업로드 완료된 기사 URL 집합(후보 제외용)."""
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT origin_url FROM articles WHERE status='업로드완료'"
        ).fetchall()
    return {r["origin_url"] for r in rows if r["origin_url"]}
