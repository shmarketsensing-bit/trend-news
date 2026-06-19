"""Notion DB 업로드. URL 중복 체크 후 저장."""
from datetime import datetime

from notion_client import Client

import config
from core.logger import get_logger, dump_failed

logger = get_logger()
_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(auth=config.NOTION_API_KEY)
    return _client


def url_exists(url: str) -> bool:
    """동일 URL이 이미 존재하는지. 실패 시 False(업로드는 진행).

    notion-client 버전에 따라 databases.query / databases().query /
    request() 중 동작하는 방식이 달라, 순서대로 시도한다.
    """
    if not url:
        return False
    url_field = config.NOTION_FIELDS["url"]
    flt = ({"property": url_field, "url": {"equals": url}}
           if config.NOTION_URL_TYPE == "url"
           else {"property": url_field, "rich_text": {"equals": url}})
    client = _get_client()
    db_id = config.NOTION_DATABASE_ID

    # 방식 1: databases.query (구버전)
    try:
        res = client.databases.query(database_id=db_id, filter=flt, page_size=1)
        return len(res.get("results", [])) > 0
    except (AttributeError, TypeError):
        pass
    except Exception as e:
        logger.warning("Notion 중복조회 실패(무시하고 진행): %s", e)
        return False

    # 방식 2: 범용 request (신버전)
    try:
        res = client.request(
            path=f"databases/{db_id}/query", method="POST",
            body={"filter": flt, "page_size": 1},
        )
        return len(res.get("results", [])) > 0
    except Exception as e:
        logger.warning("Notion 중복조회 실패(무시하고 진행): %s", e)
        return False


def _build_properties(row: dict) -> dict:
    """SQLite row(dict) → Notion properties. 필드명은 config.NOTION_FIELDS 매핑 사용."""
    F = config.NOTION_FIELDS
    url = row.get("origin_url") or row.get("naver_url") or ""
    hashtags = row.get("hashtags") or []
    if isinstance(hashtags, str):
        hashtags = [hashtags]
    tags = [t.lstrip("#").strip() for t in hashtags if t.strip()]

    # 작성자: DB 타입에 맞춰 직렬화
    author_val = row.get("author") or "Claude"
    if config.NOTION_AUTHOR_TYPE == "multi_select":
        author_prop = {"multi_select": [{"name": author_val[:100]}]}
    else:
        author_prop = {"rich_text": [{"text": {"content": author_val}}]}

    # URL: DB 타입에 맞춰 직렬화
    if config.NOTION_URL_TYPE == "url":
        url_prop = {"url": url or None}
    else:
        url_prop = {"rich_text": [{"text": {"content": url}}]}

    props: dict = {
        F["title"]: {"title": [{"text": {"content": (row.get("title") or "")[:200]}}]},
        F["category"]: {"select": {"name": row.get("category") or "기타"}},
        F["comment"]: {"rich_text": [{"text": {"content": (row.get("comment") or "")[:1900]}}]},
        F["url"]: url_prop,
        F["hashtags"]: {"multi_select": [{"name": t[:100]} for t in tags[:10]]},
        F["author"]: author_prop,
    }

    # 스크랩 날짜(수집일) — 필수 취급. 날짜만(YYYY-MM-DD) 전송.
    collected = row.get("collected_at") or ""
    scrap_date = collected[:10] if collected else None
    if scrap_date:
        props[F["collected_at"]] = {"date": {"start": scrap_date}}

    # ── 확장 필드: DB에 해당 속성이 없으면 include_extended=False로 제외 ──
    if row.get("press"):
        props[F["press"]] = {"rich_text": [{"text": {"content": row["press"][:100]}}]}
    if row.get("published_at"):
        props[F["published_at"]] = {"date": {"start": row["published_at"]}}
    if row.get("total") is not None:
        props[F["total"]] = {"number": int(row["total"])}
    if row.get("reason"):
        props[F["reason"]] = {"rich_text": [{"text": {"content": row["reason"][:1900]}}]}
    if row.get("memo"):
        props[F["memo"]] = {"rich_text": [{"text": {"content": row["memo"][:1900]}}]}
    props[F["upload_status"]] = {"select": {"name": "업로드완료"}}
    return props


def upload_row(row: dict, include_extended: bool = True) -> str:
    """
    단건 업로드. 반환: 'uploaded' | 'duplicate' | 'failed'
    include_extended=False면 필수 6필드만 사용(확장 필드 미존재 DB 대응).
    """
    url = row.get("origin_url") or row.get("naver_url") or ""
    if url_exists(url):
        return "duplicate"
    props = _build_properties(row)
    if not include_extended:
        F = config.NOTION_FIELDS
        keep = {F["title"], F["category"], F["comment"],
                F["url"], F["hashtags"], F["author"], F["collected_at"]}
        props = {k: v for k, v in props.items() if k in keep}
    try:
        _get_client().pages.create(
            parent={"database_id": config.NOTION_DATABASE_ID},
            properties=props,
        )
        return "uploaded"
    except Exception as e:
        logger.warning("Notion 업로드 실패: %s", e)
        dump_failed("notion_upload", {"title": row.get("title"), "url": url, "error": str(e)})
        return "failed"


def upload_many(rows: list[dict], include_extended: bool = True) -> dict:
    """다건 업로드 결과 집계. done_ids = 업로드완료+중복(=이미 노션에 있음) id."""
    result = {"uploaded": 0, "duplicate": 0, "failed": 0,
              "failed_titles": [], "done_ids": []}
    for row in rows:
        status = upload_row(row, include_extended=include_extended)
        result[status] += 1
        if status in ("uploaded", "duplicate"):
            if row.get("id") is not None:
                result["done_ids"].append(row["id"])
        if status == "failed":
            result["failed_titles"].append(row.get("title", ""))
    return result
