"""互動式日 K 與成交量圖。"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def stock_chart(df: pd.DataFrame, averages: list[int], title: str) -> go.Figure:
    dates = df.index.strftime("%Y-%m-%d").tolist()
    up, down = "#de4d54", "#169673"
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.07, row_heights=[0.76, 0.24])
    fig.add_trace(go.Candlestick(
        x=dates, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        name="日 K", increasing_line_color=up, increasing_fillcolor=up,
        decreasing_line_color=down, decreasing_fillcolor=down,
    ), row=1, col=1)
    palette = {5: "#e6a32a", 20: "#3b82f6", 60: "#9264cc"}
    for window in averages:
        fig.add_trace(go.Scatter(
            x=dates, y=df[f"MA{window}"], mode="lines", name=f"{window} 日均線",
            line={"color": palette[window], "width": 1.7}, connectgaps=False,
            hovertemplate=f"%{{x}}<br>{window} 日均線 %{{y:.2f}}<extra></extra>",
        ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=dates, y=df["Volume"], name="成交量（股）",
        marker_color=[up if c >= o else down for o, c in zip(df["Open"], df["Close"])],
        opacity=0.65, hovertemplate="%{x}<br>成交量 %{y:,.0f} 股<extra></extra>",
    ), row=2, col=1)
    # 用類別軸只呈現資料實際存在的交易日，不補齊週末或國定假日。
    tick_every = max(1, len(dates) // 8)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=dates,
                     tickmode="array", tickvals=dates[::tick_every],
                     showgrid=False, rangeslider_visible=False)
    fig.update_yaxes(title_text="價格（新台幣）", row=1, col=1, gridcolor="#edf0f2")
    fig.update_yaxes(title_text="成交量（股）", row=2, col=1, gridcolor="#edf0f2")
    fig.update_layout(
        title={"text": title, "font": {"size": 15}}, height=590,
        margin={"l": 16, "r": 16, "t": 60, "b": 20},
        template="plotly_white", paper_bgcolor="white", plot_bgcolor="white",
        font={"family": "Arial, PingFang TC, Microsoft JhengHei, sans-serif", "color": "#314353"},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        hovermode="x unified", dragmode="pan", uirevision=title,
    )
    return fig


def revenue_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """營收用億元，成長率用百分點；缺值保持空白。"""
    months = df.index.astype(str).tolist()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.10, row_heights=[0.65, 0.35])
    fig.add_trace(go.Bar(
        x=months, y=df["Revenue"] / 100_000_000, name="單月營收",
        marker_color="#137c71", hovertemplate="%{x}<br>單月營收 %{y:,.2f} 億元<extra></extra>",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=months, y=df["PreviousYear"] / 100_000_000, name="去年同月營收",
        mode="lines+markers", line={"color": "#e6a32a", "width": 2}, connectgaps=False,
        hovertemplate="%{x}<br>去年同月營收 %{y:,.2f} 億元<extra></extra>",
    ), row=1, col=1)
    for col, name, color in [("YoY", "年增率", "#3b82f6"), ("MoM", "月增率", "#9264cc")]:
        fig.add_trace(go.Scatter(
            x=months, y=df[col], name=name, mode="lines+markers", connectgaps=False,
            line={"color": color, "width": 1.7},
            hovertemplate=f"%{{x}}<br>{name} %{{y:+.2f}}%<extra></extra>",
        ), row=2, col=1)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=months,
                     showgrid=False, tickangle=-35)
    fig.update_yaxes(title_text="營收（億元）", row=1, col=1, gridcolor="#edf0f2")
    fig.update_yaxes(title_text="成長率（%）", row=2, col=1, gridcolor="#edf0f2", zeroline=True)
    fig.update_layout(
        title={"text": title, "font": {"size": 15}}, height=620,
        margin={"l": 16, "r": 16, "t": 80, "b": 20}, template="plotly_white",
        font={"family": "Arial, PingFang TC, Microsoft JhengHei, sans-serif", "color": "#314353"},
        legend={"orientation": "h", "y": 1.13, "x": 0}, hovermode="x unified",
        paper_bgcolor="white", plot_bgcolor="white", uirevision=title,
    )
    return fig
