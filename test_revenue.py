"""營收數值、錯誤路徑與跨頁操作；不依賴外部網路。"""
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest

import revenue_data
import stock_data
from charts import revenue_chart
from revenue_data import (
    calculate_revenue, clean_revenue, demo_revenue, fetch_revenue,
    normalize_company_code, revenue_csv, select_revenue_period,
)
from stock_data import DataError


def row(year, month, amount, code="2330"):
    return {"stock_id": code, "revenue_year": year, "revenue_month": month,
            "revenue": amount, "date": "2030-01-01", "create_time": "2030-02-01"}


@pytest.mark.parametrize("value,expected", [(" 2330 ", "2330"), ("2330.tw", "2330"),
                                           ("6488.TWO", "6488"), ("910322", "910322")])
def test_company_codes(value, expected):
    assert normalize_company_code(value) == expected


@pytest.mark.parametrize("value", ["0050", "006208", "台積電", "2330.US", "", "2330;ls"])
def test_etfs_and_invalid_company_codes(value):
    with pytest.raises(DataError):
        normalize_company_code(value)


def test_month_belongs_to_revenue_not_api_date_and_exact_growth():
    rows = [row(2024, m, 100) for m in range(1, 13)]
    rows += [row(2025, 1, 150), row(2025, 2, 180)]
    frame = calculate_revenue(clean_revenue(rows[::-1], "2330"))
    assert str(frame.index[-1]) == "2025-02"  # 不可用 2030 年 date/create_time。
    assert frame.iloc[-1].MoM == pytest.approx(20)
    assert frame.iloc[-1].YoY == pytest.approx(80)
    assert frame.iloc[-1].YTD == 330
    assert frame.iloc[-1].YTDYoY == pytest.approx(65)
    assert frame.loc["2025-01", "YTD"] == 150  # 1 月重新開始累計。


def test_missing_month_is_not_mistaken_for_previous_month():
    rows = [row(2024, m, 100) for m in range(1, 13)]
    rows += [row(2025, 1, 200), row(2025, 3, 300)]
    frame = calculate_revenue(clean_revenue(rows, "2330"))
    assert pd.isna(frame.loc["2025-02", "Revenue"])
    assert pd.isna(frame.loc["2025-03", "MoM"])
    assert frame.loc["2025-03", "YoY"] == 200
    assert pd.isna(frame.loc["2025-03", "YTD"])
    assert pd.isna(frame.loc["2025-03", "YTDYoY"])


@pytest.mark.parametrize("base", [0, -10])
def test_nonpositive_comparison_base_is_not_infinite_growth(base):
    frame = calculate_revenue(clean_revenue([row(2024, 1, base), row(2024, 2, 100),
                                             row(2025, 1, 200)], "2330"))
    assert pd.isna(frame.loc["2024-02", "MoM"])
    assert pd.isna(frame.loc["2025-01", "YoY"])
    assert pd.isna(frame.loc["2025-01", "YTDYoY"])


def test_incomplete_first_year_does_not_report_partial_ytd():
    frame = calculate_revenue(clean_revenue([row(2024, 11, 10), row(2024, 12, 20)], "2330"))
    assert pd.isna(frame.iloc[-1].YTD)


@pytest.mark.parametrize("rows", [[], None, ["invalid"], [{"stock_id": "2330"}],
    [row(2024, 13, 100)], [row(2024.5, 1, 100)], [row(2024, 1, float("inf"))],
    [row(2024, 1, None)], [row(2024, 1, 100, "2317")]])
def test_bad_data_is_not_plotted(rows):
    with pytest.raises(DataError):
        clean_revenue(rows, "2330")


def test_duplicate_same_value_is_safe_but_conflicting_values_are_not():
    assert len(clean_revenue([row(2024, 1, 100), row(2024, 1, 100)], "2330")) == 1
    with pytest.raises(DataError, match="不同營收數值"):
        clean_revenue([row(2024, 1, 100), row(2024, 1, 101)], "2330")


def test_visible_window_uses_warmup_and_chart_and_csv_units():
    full = calculate_revenue(demo_revenue())
    visible = select_revenue_period(full, 12)
    assert len(visible) == 12
    assert visible.YoY.notna().all()
    figure = revenue_chart(visible, "DEMO 虛構營收")
    assert len(figure.data) == 4
    assert figure.data[0].y[-1] == pytest.approx(visible.Revenue.iloc[-1] / 100_000_000)
    assert figure.data[2].y[-1] == pytest.approx(visible.YoY.iloc[-1])
    output = revenue_csv(visible, "DEMO", "虛構示範營收")
    assert output.startswith(b"\xef\xbb\xbf")
    table = pd.read_csv(BytesIO(output))
    assert table.iloc[-1]["月營收_新台幣元"] == visible.Revenue.iloc[-1]
    assert table.iloc[-1]["公司代號"] == "DEMO"
    assert table.iloc[-1]["資料來源"] == "虛構示範營收"


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("HTTP error")

    def json(self):
        return self.payload


def test_api_query_and_token_are_sent_in_header(monkeypatch):
    calls = []
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response({"status": 200, "data": [row(2024, 1, 100)]})
    monkeypatch.setattr(revenue_data.requests, "get", fake_get)
    frame, _ = fetch_revenue("2330.TW", "private-token")
    assert frame.iloc[0].Revenue == 100
    args = calls[0][1]
    assert args["params"]["data_id"] == "2330"
    assert args["params"]["dataset"] == "TaiwanStockMonthRevenue"
    assert "token" not in args["params"]
    assert args["headers"] == {"Authorization": "Bearer private-token"}


@pytest.mark.parametrize("payload,status,match", [
    ({}, 429, "額度"), ({"status": 402}, 200, "額度"),
    ({}, 401, "拒絕"), ({}, 500, "無法取得"),
    ([], 200, "格式"), ({"status": 400}, 200, "無法提供"),
    ({"status": 200, "data": []}, 200, "查無"),
])
def test_api_failures_are_clear(monkeypatch, payload, status, match):
    monkeypatch.setattr(revenue_data.requests, "get", lambda *a, **k: Response(payload, status))
    with pytest.raises(DataError, match=match):
        fetch_revenue("2330")


def test_network_timeout_does_not_return_demo(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("connection timeout")
    monkeypatch.setattr(revenue_data.requests, "get", timeout)
    with pytest.raises(DataError, match="無法取得"):
        fetch_revenue("2330")


def revenue_app(mode="離線示範", code="2330"):
    app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20)
    app.session_state["source_mode"] = "離線示範"
    app.run()
    app.session_state["revenue_source_mode"] = mode
    app.session_state["revenue_query"] = code
    app.switch_page("revenue_page.py").run()
    return app


def test_revenue_page_navigation_demo_periods_and_csv():
    app = revenue_app()
    assert not app.exception
    assert "DEMO" in app.subheader[0].value
    assert len(app.metric) == 4
    assert "虛構" in app.warning[0].value
    app.selectbox[0].set_value("近 36 個月").run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 36
    assert len(app.get("plotly_chart")) == 1
    assert len(app.get("download_button")) == 1
    app.session_state["source_mode"] = "離線示範"
    app.switch_page("price_page.py").run()
    assert not app.exception
    assert app.title[0].value == "台股日線觀察室"


def test_online_revenue_company_changes_and_etf_rejection(monkeypatch):
    calls = []
    def fake_fetch(code, token):
        calls.append(code)
        return demo_revenue(), "2026-11-17 12:00:00"
    monkeypatch.setattr(revenue_data, "fetch_revenue", fake_fetch)
    app = revenue_app("線上營收", "7777")
    assert not app.exception
    assert "7777" in app.subheader[0].value
    app.text_input[0].set_value("6488")
    app.button[0].click().run()
    assert not app.exception
    assert "6488" in app.subheader[0].value
    assert "6488" in calls
    app.text_input[0].set_value("0050")
    app.button[0].click().run()
    assert "ETF" in app.error[0].value
    assert not app.metric
    assert not app.get("plotly_chart")


def test_revenue_failure_is_visible_and_user_can_choose_demo(monkeypatch):
    def fail(code, token):
        raise DataError("測試用：營收來源無法連線")
    monkeypatch.setattr(revenue_data, "fetch_revenue", fail)
    app = revenue_app("線上營收", "6666")
    assert not app.exception
    assert "無法連線" in app.error[0].value
    assert not app.metric
    app.radio[0].set_value("離線示範").run()
    assert not app.exception
    assert "DEMO" in app.subheader[0].value


def test_revenue_page_works_even_if_stock_quotes_fail(monkeypatch):
    def fail(symbol):
        raise DataError("股價查詢失敗")
    monkeypatch.setattr(stock_data, "fetch_history", fail)
    app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20)
    app.session_state["query"] = ("8888", "TW")
    app.run()
    assert "股價查詢失敗" in app.error[0].value
    app.session_state["revenue_source_mode"] = "離線示範"
    app.switch_page("revenue_page.py").run()
    assert not app.exception
    assert "DEMO" in app.subheader[0].value
