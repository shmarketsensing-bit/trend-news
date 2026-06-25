"""Streamlit 큐레이션 화면 (하이브리드 모드).
- GitHub Actions가 매일 08:00 수집·분석 → 노션에 '후보' 상태로 업로드
- 출근 후 이 화면에서 노션의 '후보'를 불러와 검토 → '선정'/'제외'로 변경
실행: streamlit run app.py
"""
import streamlit as st

import config
from core import notion_client_wrap as notion

st.set_page_config(page_title="트렌드 뉴스 큐레이션", page_icon="📰", layout="wide")

st.title("📰 트렌드 뉴스 큐레이션")

# 키 점검
if not (config.NOTION_API_KEY and config.NOTION_DATABASE_ID):
    st.error("Notion 키/DB ID가 설정되지 않았습니다. (.env 또는 Secrets 확인)")
    st.stop()

# ── 후보 불러오기 ─────────────────────────────────
top = st.columns([2, 1, 3])
with top[0]:
    view_status = st.selectbox("보기", ["후보", "선정", "제외"], index=0)
with top[1]:
    st.write("")
    st.write("")
    if st.button("🔄 새로고침", use_container_width=True):
        st.rerun()

with st.spinner("노션에서 불러오는 중..."):
    rows = notion.fetch_candidates(status=view_status)

if not rows:
    st.info(f"'{view_status}' 상태의 기사가 없습니다. "
            "매일 08:00 자동 수집 후 '후보'가 채워집니다.")
    st.stop()

# ── 사이드바 필터 ─────────────────────────────────
st.sidebar.header("필터 · 정렬")
cats = sorted({r["category"] for r in rows if r["category"]})
sel_cats = st.sidebar.multiselect("카테고리", cats, default=cats)
sort_key = st.sidebar.selectbox("정렬", ["총점순", "제목순"])

view = [r for r in rows if (not sel_cats or r["category"] in sel_cats)]
def _score(r):
    try:
        return int(r.get("total") or 0)
    except (ValueError, TypeError):
        return 0
if sort_key == "총점순":
    view.sort(key=_score, reverse=True)
else:
    view.sort(key=lambda r: r.get("title") or "")

# ── 요약 메트릭 ───────────────────────────────────
m = st.columns(4)
m[0].metric(f"{view_status} 총", len(rows))
m[1].metric("표시 중", len(view))
st.divider()

# ── 후보 카드 ─────────────────────────────────────
for r in view:
    with st.container(border=True):
        head = st.columns([6, 1])
        with head[0]:
            st.markdown(f"**[{r['category']}] {r['title']}**")
            meta = " · ".join(filter(None, [
                r.get("press"),
                (r.get("published_at") or "")[:16].replace("T", " "),
                f"총점 {r.get('total')}" if r.get("total") else "",
            ]))
            if meta:
                st.caption(meta)
            if r.get("comment"):
                st.write(r["comment"][:200] + ("..." if len(r["comment"]) > 200 else ""))
            if r.get("hashtags"):
                st.caption(" ".join(f"#{t}" for t in r["hashtags"]))
        with head[1]:
            if r.get("origin_url"):
                st.link_button("원문", r["origin_url"], use_container_width=True)

        if r.get("reason"):
            with st.expander("추천 사유"):
                st.write(r["reason"])

        btns = st.columns(3)
        if btns[0].button("✅ 선정", key=f"sel_{r['page_id']}",
                          use_container_width=True, disabled=r["status"] == "선정"):
            if notion.set_status(r["page_id"], "선정"):
                st.toast("선정 → 노션 반영")
                st.rerun()
        if btns[1].button("🚫 제외", key=f"exc_{r['page_id']}",
                          use_container_width=True, disabled=r["status"] == "제외"):
            if notion.set_status(r["page_id"], "제외"):
                st.toast("제외 → 노션 반영 (삭제 아님, 되돌릴 수 있어요)")
                st.rerun()
        if btns[2].button("↩️ 후보로", key=f"rst_{r['page_id']}",
                          use_container_width=True, disabled=r["status"] == "후보"):
            if notion.set_status(r["page_id"], "후보"):
                st.toast("후보로 되돌림")
                st.rerun()
d