"""KOSIS(국가통계포털) 온라인간행물 신규 발간 추적.

주제별 간행물 카탈로그(전체 pubcode 목록)를 한 번 긁고, 각 pubcode마다
chapList.do를 호출해 최신 발간본을 확인한다. 비공식(내부용) API라 예고 없이
바뀔 수 있다는 점을 감안해야 한다.

PDF 본문은 파싱하지 않는다 — "시리즈명_연도" 형태의 식별자만 노션에 등록해
"이런 신규 통계 간행물이 나왔다"는 걸 담당자가 캐치하고 필요하면 직접 열어보게
하는 용도다(뉴스처럼 AI가 본문을 요약하지 않음).

각 pubcode의 chapList는 트리 구조다(lvl=0이 보통 "연도" 단위, 그 아래 분기/표별로
더 잘게 쪼개짐 — 예: 가축동향은 연도 밑에 분기, 그 밑에 축종별 통계표까지 내려감).
너무 잘게 쪼개진 항목까지 다 잡으면 노션이 지저분해지므로 lvl==0(연도 단위)만 채택한다.
lvl==0이 폴더(하위 항목만 있고 직접 받을 파일이 없는 경우)면 다운로드 링크 대신
간행물 목록 페이지로 안내한다.

독립 실행: python -m core.kosis_publications
"""
from __future__ import annotations

import re
import time
from datetime import datetime

import requests

import config
from core import notion_client_wrap as notion
from core.logger import get_logger

logger = get_logger()

_CATALOG_URL = "https://kosis.kr/upsHtml/online.do"
_CATALOG_PARAMS = {"isOnline": "Y", "isNew": "Y", "PART": "G", "dev": "Y"}
_CHAPLIST_URL = "https://kosis.kr/upsHtml/online/chapList.do"
_DOWNLOAD_URL = "https://kosis.kr/upsHtml/online/downSrvcFile.do"
_FALLBACK_URL = _CATALOG_URL + "?isOnline=Y&isNew=Y&PART=G&dev=Y"  # 폴더형 항목용 대체 링크
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

MIN_YEAR = 2025  # 이 연도 이후 발간본만 추적
CATEGORY = "통계간행물"
REQUEST_DELAY = 0.15  # pubcode별 조회 사이 대기(서버 부담 최소화)

_YEAR_RE = re.compile(r"20[12]\d")
_PUB_ROW_RE = re.compile(
    r'<span[^>]*class="varGrpNo"[^>]*>(\d+)</span>\s*'
    r'<span[^>]*class="varKorCd"[^>]*>([^<]*)</span>\s*'
    r'<a href="javascript:fn_selectPub\(\'([A-Za-z0-9]+)\'\)">\s*<span>([^<]+)',
    re.DOTALL,
)
_THEME_RE = re.compile(
    r'data-value="([^"]+)"[^>]*>\s*<span class="varKind"[^>]*>1</span>\s*'
    r'<span class="varSelValue"[^>]*>(\d+)</span>'
)
_EXT_BY_TYPE = {"P": ".pdf", "X": ".xls", "L": ".xlsx", "H": ".hwp", "O": ".hwpx", "I": ".zip"}


def fetch_catalog() -> tuple[dict[str, str], list[dict]]:
    """전체 테마(코드→이름)와 간행물 시리즈 목록(pubcode 포함)을 가져온다."""
    r = requests.get(_CATALOG_URL, params=_CATALOG_PARAMS, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    html = r.text

    themes = {code: name for name, code in _THEME_RE.findall(html)}
    pubs = [
        {"theme_code": grp, "pubcode": pubcode, "series_name": name.strip()}
        for grp, _korcd, pubcode, name in _PUB_ROW_RE.findall(html)
    ]
    logger.info("KOSIS 카탈로그: 테마 %d개, 간행물 시리즈 %d개", len(themes), len(pubs))
    return themes, pubs


def _extract_year(kor_name: str) -> int | None:
    years = [int(y) for y in _YEAR_RE.findall(kor_name)]
    return max(years) if years else None


def _download_url(pubcode: str, seq, form_id: str, form_srvc_type: str | None) -> str:
    if not form_id or not form_srvc_type:
        return _FALLBACK_URL
    ext = ".pdf"
    for ch, e in _EXT_BY_TYPE.items():
        if ch in form_srvc_type:
            ext = e
            break
    return f"{_DOWNLOAD_URL}?PUBCODE={pubcode}&SEQ={seq}&FILE_NAME={form_id}{ext}"


def fetch_recent_editions(pubcode: str, min_year: int = MIN_YEAR) -> list[dict]:
    """이 간행물 시리즈의 연도(lvl==0) 단위 항목 중 min_year 이후 것만."""
    try:
        r = requests.post(
            _CHAPLIST_URL, data={"pubcode": pubcode, "pubLevel": "3"},
            headers=_HEADERS, timeout=20,
        )
        data = r.json()
    except Exception as e:
        logger.warning("chapList 조회 실패(pubcode=%s): %s", pubcode, e)
        return []

    editions = []
    for item in data.get("chapList") or []:
        if item.get("lvl") != 0:
            continue  # 연도 단위(lvl=0)만 — 그 아래 분기/표 단위는 너무 잘게 쪼개짐
        kor_name = item.get("korName") or ""
        year = _extract_year(kor_name)
        if year is None or year < min_year:
            continue
        editions.append({
            "korName": kor_name,
            "seq": item.get("seq"),
            "formId": item.get("formId"),
            "formSrvcType": item.get("formSrvcType"),
            "year": year,
        })
    return editions


def collect_recent_publications(min_year: int = MIN_YEAR) -> list[dict]:
    """전체 카탈로그를 훑어 min_year 이후 발간본을 노션 업로드용 row로 만든다."""
    themes, pubs = fetch_catalog()
    rows = []
    for pub in pubs:
        editions = fetch_recent_editions(pub["pubcode"], min_year)
        theme_name = themes.get(pub["theme_code"], "")
        for ed in editions:
            title = f"{pub['series_name']}_{ed['year']}년"
            url = _download_url(pub["pubcode"], ed["seq"], ed["formId"], ed["formSrvcType"])
            rows.append({
                "title": title,
                "category": CATEGORY,
                "comment": title,
                "origin_url": url,
                "hashtags": [pub["series_name"], theme_name] if theme_name else [pub["series_name"]],
                "author": config.DEFAULT_AUTHOR,
                "collected_at": datetime.now().strftime("%Y-%m-%d"),
            })
        time.sleep(REQUEST_DELAY)
    logger.info("KOSIS 신규(>=%d년) 발간본 %d건 수집", min_year, len(rows))
    return rows


def main() -> int:
    if not (config.NOTION_API_KEY and config.NOTION_DATABASE_ID):
        logger.error("NOTION_API_KEY / NOTION_DATABASE_ID 누락(.env 확인). 중단.")
        return 1

    rows = collect_recent_publications()
    if not rows:
        logger.info("업로드할 신규 간행물 없음.")
        return 0

    res = notion.upload_many(rows, include_extended=config.NOTION_INCLUDE_EXTENDED, status="후보")
    logger.info("KOSIS 간행물 노션 업로드 | 신규 %d·중복 %d·실패 %d",
                res["uploaded"], res["duplicate"], res["failed"])
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
