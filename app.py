"""웹 화면: 입력칸에 종목명을 넣으면 원 페이지 리포트를 보여준다.

실행:  streamlit run app.py
"""
import streamlit as st
import streamlit.components.v1 as components

from onepager import ResolveError, make_report

st.set_page_config(page_title="원 페이지 종목 리포트", page_icon="📄", layout="wide")
st.markdown("### 📄 원 페이지 종목 리포트")
st.caption("미국 · 한국 · 일본 · 중국 · 홍콩 주식 — 종목명 또는 코드 (예: 애플, 삼성전자, 7203.T, 텐센트, 600519.SS)")

with st.form("q", clear_on_submit=False):
    col1, col2 = st.columns([5, 1])
    query = col1.text_input("종목", placeholder="종목명 입력", label_visibility="collapsed")
    go = col2.form_submit_button("리포트 만들기", use_container_width=True)


@st.cache_data(ttl=60 * 30, show_spinner=False)
def cached_report(q: str):
    return make_report(q)


if go and query.strip():
    with st.spinner(f"'{query}' 데이터 수집 중…"):
        try:
            name, html = cached_report(query.strip())
        except (ResolveError, LookupError) as ex:
            st.error(str(ex))
            st.stop()
        except Exception as ex:  # 데이터 소스 일시 오류 등
            st.error(f"리포트 생성 실패: {type(ex).__name__}: {ex}")
            st.stop()
    st.download_button("HTML 저장", html, file_name=f"{name}.html", mime="text/html")
    components.html(html, height=1900, scrolling=True)
