"""股價走勢頁；由 app.py 導覽載入。"""
from datetime import datetime

import streamlit as st

from charts import stock_chart
from stock_data import (
    DataError, MARKETS, PERIODS, TAIPEI, add_indicators, demo_history,
    export_csv, fetch_history, latest_summary, normalize_symbol, select_period,
)

@st.cache_data(ttl=900, show_spinner=False)
def load_online(symbol: str):
    return fetch_history(symbol)


with st.sidebar:
    st.markdown("### 📈 台股日線觀察室")
    st.caption("從一張 K 線，開始學 Python。")
    source_mode = st.radio("資料模式", ["線上股價", "離線示範"], key="source_mode")
    is_demo = source_mode == "離線示範"
    with st.form("query_form"):
        code = st.text_input("股票／ETF 代號", value="2330", max_chars=16,
                             disabled=is_demo, help="例如 2330、0050、006208；ETF 開頭的 0 要保留。")
        market = st.selectbox("交易市場", list(MARKETS), disabled=is_demo)
        submitted = st.form_submit_button("查詢股票", type="primary", disabled=is_demo,
                                         width="stretch")
    if "query" not in st.session_state:
        st.session_state.query = ("2330", "TW")
    if submitted:
        st.session_state.query = (code, MARKETS[market])
    period = st.selectbox("顯示期間", list(PERIODS), index=2)
    averages = st.multiselect("顯示均線", [5, 20, 60], default=[5, 20, 60],
                              format_func=lambda x: f"{x} 日均線")
    if st.button("重新取得線上資料", disabled=is_demo, width="stretch"):
        load_online.clear()
    st.divider()
    st.caption("代號範例：2330、0050（上市）。\n\n上櫃股票請切換市場。\n\n線上結果快取 15 分鐘；按重新取得可略過快取。")

st.markdown('<div class="eyebrow">TAIWAN STOCK · DAILY VIEW</div>', unsafe_allow_html=True)
st.title("台股日線觀察室")
st.write("查詢日線、觀察均線，讓股價走勢更容易閱讀。")

if is_demo:
    st.warning("離線示範｜以下是電腦產生的虛構價格，與任何真實股票無關。")
    raw = demo_history()
    symbol = "DEMO"
    display_name = "虛構示範股票"
    source = "虛構示範資料（非真實股價）"
    fetched_at = None
else:
    try:
        symbol = normalize_symbol(*st.session_state.query)
        with st.spinner(f"正在取得 {symbol} 日線資料…"):
            raw, fetched_at = load_online(symbol)
    except DataError as exc:
        st.error(str(exc))
        st.info("左側可以修改股票代號與交易市場，或切換「離線示範」先操作圖表。")
        st.stop()
    display_name = {"2330.TW": "台積電", "0050.TW": "元大台灣50",
                    "2317.TW": "鴻海", "2454.TW": "聯發科"}.get(symbol, "股票／ETF")
    source = "Yahoo Finance／yfinance（股息未還原日線）"

full = add_indicators(raw)
visible = select_period(full, period)
summary = latest_summary(full)
st.subheader(f"{symbol} · {display_name}")
st.caption(f"最新資料日期 {summary['date']} · 新台幣 · {source}")
if fetched_at:
    st.caption(f"取得時間（台北）{fetched_at}。資料可能延遲，盤中最新日 K 可能尚未完成。")
    age = (datetime.now(TAIPEI).date() - full.index[-1].date()).days
    if age > 7:
        st.warning(f"最新一筆距今已 {age} 天，請留意休市、停牌或來源更新情況。")

cards = st.columns(4)
delta = (f"{summary['change']:+.2f}（{summary['percent']:+.2f}%）"
         if summary["change"] is not None else None)
cards[0].metric("最新日線收盤價", f"{summary['close']:,.2f}", delta=delta, delta_color="inverse")
cards[1].metric("當日最高", f"{summary['high']:,.2f}")
cards[2].metric("當日最低", f"{summary['low']:,.2f}")
cards[3].metric("當日成交量（股）", f"{summary['volume']:,.0f}")
st.caption("價差與百分比：最新收盤欄位與前一筆交易日收盤欄位相比；非交易所除權息參考價漲跌幅。")

chart_tab, table_tab, learn_tab = st.tabs(["走勢圖", "歷史資料與下載", "讀圖與學習"])
with chart_tab:
    st.plotly_chart(stock_chart(visible, averages, f"{symbol} · {period} · 股息未還原日線"),
                    width="stretch", theme=None,
                    config={"displaylogo": False, "scrollZoom": False})
    st.caption("紅 K：收盤 ≥ 開盤；綠 K：收盤 < 開盤。拖曳移動，使用工具列縮放，雙擊還原。")
    if full["MA60"].isna().all():
        st.info("歷史資料不足 60 筆，60 日均線尚無法計算。")

with table_tab:
    st.write(f"顯示 {len(visible):,} 筆日線，{visible.index[0]:%Y-%m-%d} 至 {visible.index[-1]:%Y-%m-%d}。")
    output = export_csv(visible, symbol, source)
    st.download_button("下載這段期間的 CSV", output,
                       file_name=f"{symbol}_{visible.index[-1]:%Y%m%d}{'_synthetic' if is_demo else ''}.csv",
                       mime="text/csv")
    table = visible.rename(columns={"Open": "開盤", "High": "最高", "Low": "最低",
                                    "Close": "收盤", "Volume": "成交量（股）",
                                    "MA5": "5日均線", "MA20": "20日均線", "MA60": "60日均線"}).copy()
    table.index = table.index.strftime("%Y-%m-%d")
    table.index.name = "日期"
    st.dataframe(table.iloc[::-1], width="stretch")

with learn_tab:
    st.markdown("""
**怎麼讀這張圖？**

- K 線呈現一天的開盤、最高、最低、收盤；上下細線是當日價格範圍。
- 5／20／60 日均線是最近 5／20／60 筆交易日收盤價的平均。
- 下方成交量的單位是股；均線先用完整歷史計算，再裁切到選定期間。
- 價格未作股息還原，來源可能已處理股票分割；不能直接當成投資總報酬。

**想學 Python，依這個順序看程式：**

1. `stock_data.py`：查詢資料、整理日期、計算均線。
2. `charts.py`：把日線與成交量變成互動圖表。
3. `price_page.py`：股價操作畫面；`app.py`：股價與營收頁面導覽。

示範模式僅排除週末，沒有套用台股國定假日；所有價格、量及指標都是虛構。
""")
st.divider()
st.caption("個人學習與日線觀察工具 · 非即時行情 · 實際成交請以券商及交易所資訊為準。")
