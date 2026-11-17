"""不用連網的計算與操作驗證。執行 python -m pytest -q。"""
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import stock_data
from charts import stock_chart
from stock_data import (
    DataError, add_indicators, clean_history, demo_history, export_csv,
    latest_summary, normalize_symbol, select_period,
)


@pytest.mark.parametrize("code,market,expected", [
    ("2330", "TW", "2330.TW"), (" 0050 ", "TW", "0050.TW"),
    ("006208", "TW", "006208.TW"), ("6488.two", "TWO", "6488.TWO"),
    ("00679b", "TWO", "00679B.TWO"),
])
def test_codes(code, market, expected):
    assert normalize_symbol(code, market) == expected


@pytest.mark.parametrize("code,market", [("台積電", "TW"), ("2330.TWO", "TW"),
                                         ("AAPL", "TW"), ("", "TW"), ("0050", "US")])
def test_bad_codes(code, market):
    with pytest.raises(DataError):
        normalize_symbol(code, market)


def test_rolling_averages_use_history_before_display_period():
    dates = pd.bdate_range("2025-01-01", periods=180)
    frame = pd.DataFrame({"Close": range(1, 181)}, index=dates)
    full = add_indicators(frame)
    assert pd.isna(full.iloc[58].MA60)
    assert full.iloc[59].MA60 == pytest.approx(30.5)
    visible = select_period(full, "1 個月")
    assert not pd.isna(visible.iloc[0].MA60)
    assert visible.iloc[-1].MA5 == pytest.approx(178)


def test_date_normalization_sorting_and_duplicates():
    raw = demo_history().iloc[:3]
    raw.index = raw.index.tz_localize("Asia/Taipei").tz_convert("UTC")
    raw = pd.concat([raw.iloc[::-1], raw.iloc[[1]]])
    result = clean_history(raw)
    assert len(result) == 3
    assert result.index.is_monotonic_increasing
    assert result.index.tz is None
    assert result.index[0] == demo_history().index[0]


@pytest.mark.parametrize("column,value", [("Close", float("nan")),
    ("High", float("inf")), ("Volume", -100), ("Close", 0), ("High", 0.01)])
def test_invalid_data_is_not_silently_plotted(column, value):
    raw = demo_history()
    raw.iloc[0, raw.columns.get_loc(column)] = value
    with pytest.raises(DataError):
        clean_history(raw)


def test_empty_and_missing_columns():
    for frame in [pd.DataFrame(), demo_history().drop(columns="Volume")]:
        with pytest.raises(DataError):
            clean_history(frame)


def test_change_and_one_day_case():
    frame = pd.DataFrame({"Close": [100., 105.], "Volume": [10, 20],
                          "High": [101., 106.], "Low": [99., 104.]},
                         index=pd.to_datetime(["2025-01-02", "2025-01-03"]))
    summary = latest_summary(frame)
    assert summary["change"] == 5
    assert summary["percent"] == 5
    assert latest_summary(frame.iloc[:1])["change"] is None


def test_chart_and_csv_keep_demo_identity_and_volume_units():
    frame = select_period(add_indicators(demo_history()), "3 個月")
    figure = stock_chart(frame, [5, 20, 60], "DEMO 虛構")
    assert len(figure.data) == 5
    assert list(figure.data[-1].y) == list(frame.Volume)
    assert figure.layout.xaxis.type == "category"
    assert figure.data[-1].name == "成交量（股）"
    exported = export_csv(frame, "DEMO", "虛構示範資料")
    assert exported.startswith(b"\xef\xbb\xbf")
    text = exported.decode("utf-8-sig")
    assert "DEMO,虛構示範資料" in text
    assert "成交量_股" in text


def make_app():
    return AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=20)


def test_offline_app_controls():
    app = make_app()
    app.session_state["source_mode"] = "離線示範"
    app.run()
    assert not app.exception
    assert len(app.metric) == 4
    assert "DEMO" in app.subheader[0].value
    assert "虛構" in app.warning[0].value
    app.selectbox[1].set_value("1 個月").run()
    app.multiselect[0].set_value([20]).run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 1
    assert len(app.get("download_button")) == 1


def test_online_success_uses_selected_symbol(monkeypatch):
    calls = []
    def fake_fetch(symbol):
        calls.append(symbol)
        return demo_history(), "2026-10-30 15:00:00"
    monkeypatch.setattr(stock_data, "fetch_history", fake_fetch)
    app = make_app().run()
    assert not app.exception
    assert "2330.TW" in app.subheader[0].value
    app.text_input[0].set_value("0050")
    app.button[0].click().run()
    assert not app.exception
    assert "0050.TW" in app.subheader[0].value
    assert "0050.TW" in calls
    # 市場後綴不符時顯示錯誤，不保留舊股票圖表。
    app.text_input[0].set_value("0050.TWO")
    app.button[0].click().run()
    assert "市場不符" in app.error[0].value
    assert not app.get("plotly_chart")


def test_online_failure_never_becomes_demo(monkeypatch):
    def failing_fetch(symbol):
        raise DataError("測試用：無法取得線上資料")
    monkeypatch.setattr(stock_data, "fetch_history", failing_fetch)
    app = make_app()
    # 與成功路徑使用不同查詢，避開跨 AppTest 的資料快取。
    app.session_state["query"] = ("9999", "TW")
    app.run()
    assert not app.exception
    assert "無法取得" in app.error[0].value
    assert not app.metric
    assert not app.get("plotly_chart")
    app.radio[0].set_value("離線示範").run()
    assert not app.exception
    assert "DEMO" in app.subheader[0].value
    assert "虛構" in app.warning[0].value
