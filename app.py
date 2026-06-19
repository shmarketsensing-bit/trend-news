"""Streamlit 큐레이션 화면.
실행: streamlit run app.py
"""
import subprocess
import sys
from datetime import datetime

import streamlit as st

import config
from core import db, notion_client_wrap as notion

st.set_page_config(page_title="트렌드 뉴스 큐레이션", page_icon="📰", layout="wide")
db.init_db()

# ── 헤더 ──────────────────────────────────────────
st.title("📰 트렌드 뉴스 큐레이션")

dates = db.list_run_dates()
top = st.columns([2, 1, 3])
with top[0]:
    run_date = st.selectbox(
        "수집 날짜", dates,
        index=0 if dates else None,
        placeholder="수집된 날짜 없음",
    ) if dates else None
with top[1]:
    st.write("")          # 라벨 높이만큼 띄워 버튼을 드롭다운과 같은 줄에 정렬
    st.write("")
    recollect = st.button("🔄 지금 재수집", use_container_width=True)

if recollect:
    with st.spinner("수집 배치 실행 중... (수 분 소요)"):
        proc = subprocess.run(
            [sys.executable, "run_collect.py"],
            cwd=str(config.BASE_DIR), capture_output=True, text=True,
        )
    if proc.returncode == 0:
        st.success("재수집 완료. 새로고침하세요.")
    else:
        st.error("재수집 실패. logs/ 확인.")
        st.code(proc.stderr[-1500:] or proc.stdout[-1500:])

if not run_date:
    st.info("아직 수집된 후보가 없습니다. [지금 재수집] 또는 08:00 배치를 기다려주세요.")
    st.stop()

rows = db.fetch_by_date(run_date)

# ── 사이드바: 필터 ────────────────────────────────
st.sidebar.header("필터 · 정렬")
cats = sorted({r["category"] for r in rows if r["category"]})
sel_cats = st.sidebar.multiselect("카테고리", cats, default=cats)
status_filter = st.sidebar.multiselect(
    "상태", ["후보", "선정", "제외", "업로드완료"],
    default=["후보", "선정"],
)
sort_key = st.sidebar.selectbox("정렬", ["총점순", "발행일순"])
include_ext = st.sidebar.checkbox(
    "Notion 확장 필드 포함", value=False,
    help="언론사/발행일시/점수/추천사유/메모 등. DB에 해당 속성이 없으면 끈 채로 두세요.",
)

view = [r for r in rows
        if (not sel_cats or r["category"] in sel_cats)
        and (not status_filter or r["status"] in status_filter)]
if sort_key == "발행일순":
    view.sort(key=lambda r: r.get("published_at") or "", reverse=True)
else:
    view.sort(key=lambda r: r.get("total") or 0, reverse=True)

# ── 업로드 처리 함수 (상단/하단 공용) ─────────────
def do_upload():
    sel = db.fetch_selected(run_date)
    if not sel:
        st.warning("선정된 기사가 없습니다.")
        return
    if not (config.NOTION_API_KEY and config.NOTION_DATABASE_ID):
        st.error("Notion 키/DB ID가 .env에 없습니다.")
        return
    with st.spinner("업로드 중..."):
        res = notion.upload_many(sel, include_extended=include_ext)
        for aid in res.get("done_ids", []):
            db.update_status(aid, "업로드완료")
    st.success(f"업로드 {res['uploaded']} · 중복 {res['duplicate']} · 실패 {res['failed']}")
    if res["failed_titles"]:
        st.warning("실패 기사:\n- " + "\n- ".join(res["failed_titles"]))
    st.rerun()

# ── 상단 요약 + 업로드 (한 줄) ────────────────────
n_sel = sum(1 for r in rows if r["status"] == "선정")
n_done = sum(1 for r in rows if r["status"] == "업로드완료")
mcols = st.columns([1, 1, 1, 1, 3])
mcols[0].metric("후보 총", len(rows))
mcols[1].metric("선정", n_sel)
mcols[2].metric("업로드완료", n_done)
mcols[3].metric("표시 중", len(view))
with mcols[4]:
    st.write("")
    if st.button(f"📤 선정 {n_sel}건 Notion 업로드", type="primary", 
                 use_container_width=False, disabled=n_sel == 0,
                 key="upload_top"):
        do_upload()

st.divider()

# ── 후보 카드 ─────────────────────────────────────
for r in view:
    with st.container(border=True):
        head = st.columns([6, 1])
        with head[0]:
            badge = {"선정": "✅", "제외": "🚫", "업로드완료": "📤"}.get(r["status"], "🟡")
            st.markdown(f"**{badge} [{r['category']}] {r['title']}**")
            meta = " · ".join(filter(None, [
                r.get("press"),
                (r.get("published_at") or "")[:16].replace("T", " "),
                f"총점 {r.get('total', 0)}/20",
                f"중복 {r.get('duplicate_count', 1)}건" if r.get("duplicate_count", 1) > 1 else "",
            ]))
            st.caption(meta)
            if r.get("summary"):
                st.write(r["summary"])
            if r.get("hashtags"):
                st.caption(" ".join(r["hashtags"]))
        with head[1]:
            if r.get("origin_url"):
                st.link_button("원문", r["origin_url"], use_container_width=True)

        with st.expander("상세 · 점수 · 메모"):
            st.markdown(f"**코멘트 요약** — {r.get('comment', '')}")
            st.markdown(f"**카드사/소비시장 시사점** — {r.get('implication', '')}")
            st.markdown(
                f"**점수** — 트렌드 {r.get('score_trend', 0)} · "
                f"비즈니스 {r.get('score_business', 0)} · "
                f"신규성 {r.get('score_novelty', 0)} · "
                f"확산 {r.get('score_spread', 0)}  → **{r.get('total', 0)}/20**"
            )
            st.markdown(f"**추천 사유** — {r.get('reason', '')}")
            if r.get("body_source") == "naver":
                st.caption("ℹ️ 본문 추출 실패 → 네이버 요약문 기반 분석")

            memo = st.text_input("담당자 메모", value=r.get("memo", ""),
                                 key=f"memo_{r['id']}")
            if memo != r.get("memo", ""):
                db.update_memo(r["id"], memo)

        btns = st.columns(3)
        if btns[0].button("✅ 선정", key=f"sel_{r['id']}",
                          use_container_width=True,
                          disabled=r["status"] == "업로드완료"):
            db.update_status(r["id"], "선정")
            st.rerun()
        if btns[1].button("🚫 제외", key=f"exc_{r['id']}",
                          use_container_width=True,
                          disabled=r["status"] == "업로드완료"):
            db.update_status(r["id"], "제외")
            st.rerun()
        if btns[2].button("↩️ 후보로", key=f"rst_{r['id']}",
                          use_container_width=True,
                          disabled=r["status"] == "업로드완료"):
            db.update_status(r["id"], "후보")
            st.rerun()

st.divider()
