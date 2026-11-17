"""啟動：python -m streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="台股觀察室", page_icon="📈", layout="wide")
st.markdown("""
<style>
.block-container {padding-top:2rem; max-width:1440px;}
h1 {letter-spacing:-.045em; color:#163b3a;}
[data-testid="stMetric"] {background:#fff; border:1px solid #e2eae9;
    border-radius:14px; padding:18px 20px; min-height:128px;}
[data-testid="stMetricValue"] {font-size:1.8rem;}
[data-testid="stSidebar"] {background:#f1f6f4;}
.eyebrow {color:#137c71; font-size:12px; font-weight:700; letter-spacing:.16em;}
</style>
""", unsafe_allow_html=True)

page = st.navigation([
    st.Page("price_page.py", title="股價走勢", icon="📈", default=True),
    st.Page("revenue_page.py", title="月營收", icon="📊"),
])
page.run()
