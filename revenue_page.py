"""月營收頁；只有選到此頁才查詢營收，不依賴 Yahoo 股價可用性。"""
import streamlit as st
import pandas as pd

from charts import revenue_chart
from revenue_data import (
    REVENUE_PERIODS, calculate_revenue, demo_revenue, fetch_revenue,
    normalize_company_code, revenue_csv, select_revenue_period,
)
from stock_data import DataError


@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def load_revenue(code: str, token: str):
    return fetch_revenue(code, token)


def percent(value):
    return f"{value:+.2f}%" if pd.notna(value) else "—"


with st.sidebar:
    st.markdown("### 📊 公司月營收")
    mode = st.radio("資料模式", ["線上營收", "離線示範"],
                    index=1 if st.session_state.get("source_mode") == "離線示範" else 0,
                    key="revenue_source_mode")
    is_demo = mode == "離線示範"
    if "revenue_query" not in st.session_state:
        st.session_state.revenue_query = st.session_state.get("query", ("2330", "TW"))[0]
    if "revenue_company_input" not in st.session_state:
        st.session_state.revenue_company_input = st.session_state.revenue_query
    with st.form("revenue_query_form"):
        code = st.text_input("公司代號", key="revenue_company_input", max_chars=16, disabled=is_demo,
                             help="例如 2330、2317、6488；上市與上櫃公司都可查，ETF 不適用。")
        submitted = st.form_submit_button("查詢營收", type="primary", width="stretch", disabled=is_demo)
    if submitted:
        st.session_state.revenue_query = code
    period = st.selectbox("營收顯示期間", list(REVENUE_PERIODS), index=1)
    with st.expander("進階設定（選填）"):
        token = st.text_input("FinMind Token", type="password", key="revenue_token", disabled=is_demo,
                              help="不填可先匿名查詢；Token 只在目前執行中的工作階段使用，不寫入檔案。")
        st.caption("查詢受 FinMind 使用額度與服務狀態影響。")
    if st.button("重新取得營收資料", width="stretch", disabled=is_demo):
        load_revenue.clear()
    st.divider()
    st.caption("營收結果快取 1 小時；按重新取得可略過快取。\n\n此頁獨立查詢營收，不需要先取得股價。")

st.markdown('<div class="eyebrow">TAIWAN STOCK · MONTHLY REVENUE</div>', unsafe_allow_html=True)
st.title("公司月營收")
st.write("把每月營收與去年同月放在一起，觀察營運規模與成長變化。")
if is_demo:
    st.warning("離線示範｜所有營收與成長率均來自虛構資料，與任何真實公司無關。")
    raw, fetched_at = demo_revenue(), None
    code = "DEMO"
    source = "虛構示範營收（非真實公司）"
else:
    try:
        code = normalize_company_code(st.session_state.revenue_query)
        with st.spinner(f"正在取得 {code} 月營收…"):
            raw, fetched_at = load_revenue(code, token)
    except DataError as exc:
        st.error(str(exc))
        st.info("可在左側修改公司代號、重新取得資料，或切換「離線示範」練習。")
        st.stop()
    source = "FinMind／TaiwanStockMonthRevenue"

full = calculate_revenue(raw)
visible = select_revenue_period(full, REVENUE_PERIODS[period])
last = full.iloc[-1]
name = {"2330": "台積電", "2317": "鴻海", "2454": "聯發科", "DEMO": "虛構示範公司"}.get(code, "公司")
st.subheader(f"{code} · {name}")
st.caption(f"最新營收月份 {full.index[-1]} · 來源：{source}")
if fetched_at:
    st.caption(f"取得時間（台北）{fetched_at}。營收月份與資料取得日期不同，最新公告可能尚未收錄。")
    expected_latest = pd.Period(pd.Timestamp.now(tz="Asia/Taipei").date(), freq="M") - 1
    gap = expected_latest.ordinal - full.index[-1].ordinal
    if gap > 1:
        st.warning("最新營收月份落後兩個月以上，請確認來源更新情況或公司公告。")

cards = st.columns(4)
cards[0].metric("單月營收（億元）", f"{last.Revenue / 100_000_000:,.2f}")
cards[1].metric("月增率 MoM", percent(last.MoM))
cards[2].metric("年增率 YoY", percent(last.YoY))
cards[3].metric("當年累計營收（億元）", f"{last.YTD / 100_000_000:,.2f}" if pd.notna(last.YTD) else "—",
                help="最新月份所屬年度，從 1 月加總到該月；缺月則不計算。")
st.caption(f"累計年增率 {percent(last.YTDYoY)} · 1 億元＝100,000,000 元；成長率以未四捨五入的元資料計算。")
if visible.Revenue.isna().any():
    st.warning("這段期間部分月份沒有資料，圖表保留空缺，不視為零；相關成長率／累計可能無法計算。")

chart_tab, table_tab, help_tab = st.tabs(["營收走勢", "營收明細與下載", "指標說明"])
with chart_tab:
    st.plotly_chart(revenue_chart(visible, f"{code} · {period}"), width="stretch", theme=None,
                    config={"displaylogo": False, "scrollZoom": False})
    st.caption("柱狀圖為單月營收，折線為去年同月營收；下方顯示年增率及月增率。")
with table_tab:
    st.download_button("下載營收 CSV", revenue_csv(visible, code, source),
                       file_name=f"{code}_revenue_{full.index[-1]}{'_synthetic' if is_demo else ''}.csv",
                       mime="text/csv")
    table = visible.copy()
    for col in ("Revenue", "PreviousYear", "YTD"):
        table[col] = table[col] / 100_000_000
    table.index = table.index.astype(str)
    table.index.name = "營收月份"
    table = table.rename(columns={"Revenue": "單月營收（億元）", "PreviousYear": "去年同月（億元）",
                                  "MoM": "月增率（%）", "YoY": "年增率（%）",
                                  "YTD": "當年累計（億元）", "YTDYoY": "累計年增率（%）"})
    st.dataframe(table.iloc[::-1].round(2), width="stretch")
    st.caption("畫面金額為億元；下載 CSV 保留新台幣元。空白代表無法計算或資料未提供。")
with help_tab:
    st.markdown("""
- **月增率（MoM）**＝（本月營收 − 前月營收）÷ 前月營收 × 100%。
- **年增率（YoY）**＝（本月營收 − 去年同月營收）÷ 去年同月營收 × 100%。
- **當年累計營收**：最新營收月份所屬年度，從 1 月到該月的合計，不是滾動 12 個月。
- **累計年增率**：本年度截至該月的累計，與去年相同月份範圍比較。
- 若比較基期缺資料、為零或負值，成長率以「—」顯示；累計缺月也不強行加總。
- 依實際年月對齊資料；缺少 2 月時，3 月不會拿 1 月假裝前月比較。
- 此頁查詢**公司月營收**，不是獲利、EPS 或 ETF 配息。公司若有更正，資料可能變動。
- FinMind 的 `date` 不能當成實際公告日；`create_time` 是資料入庫日期，也不是正式公告日期。

資料文件：[FinMind 月營收](https://finmind.github.io/tutor/TaiwanMarket/Fundamental/)。
營收與股價資料來源不同，可能各自更新或各自暫時無法連線。
""")
st.divider()
st.caption("月營收觀察工具 · 金額為新台幣 · 詳細數據請核對公司與公開資訊觀測站公告。")
