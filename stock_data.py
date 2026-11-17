"""台股日線資料與均線：與畫面分開，方便學習及驗證。"""
from __future__ import annotations

from datetime import datetime
from math import isfinite
import random
import re
from zoneinfo import ZoneInfo

import pandas as pd

TAIPEI = ZoneInfo("Asia/Taipei")
OHLCV = ["Open", "High", "Low", "Close", "Volume"]
PERIODS = {"1 個月": 1, "3 個月": 3, "6 個月": 6, "1 年": 12, "2 年": 24}
MARKETS = {"上市（TW）": "TW", "上櫃（TWO）": "TWO"}


class DataError(ValueError):
    """可直接顯示給使用者的資料錯誤。"""


def normalize_symbol(code: str, market: str) -> str:
    """保留 ETF 開頭的 0；已有後綴時檢查是否符合選定市場。"""
    code = code.strip().upper()
    if market not in {"TW", "TWO"}:
        raise DataError("請選擇上市或上櫃市場。")
    if "." in code:
        base, suffix = code.rsplit(".", 1)
        if suffix != market:
            raise DataError("代號後綴與市場不符，請調整市場，或只輸入不含後綴的代號。")
        code = base
    if not re.fullmatch(r"[0-9]{4,6}[A-Z]?", code):
        raise DataError("請輸入台股代號，例如 2330、0050、006208；不要輸入公司名稱。")
    return f"{code}.{market}"


def clean_history(raw: pd.DataFrame) -> pd.DataFrame:
    """檢查資料、轉成台北日期；不補造交易日或價格。"""
    if raw is None or raw.empty:
        raise DataError("查無日線資料，請檢查代號及上市／上櫃市場，稍後再試。")
    if not set(OHLCV).issubset(raw.columns):
        raise DataError("資料來源缺少開高低收或成交量，暫時無法繪圖。")
    df = raw[OHLCV].copy()
    try:
        dates = pd.to_datetime(df.index, errors="raise")
        if dates.tz is not None:
            dates = dates.tz_convert(TAIPEI).tz_localize(None)
        df.index = dates.normalize()
    except (ValueError, TypeError, AttributeError) as exc:
        raise DataError("資料來源的日期格式不正確。") from exc
    if df.index.hasnans:
        raise DataError("資料來源含有無效日期。")
    df.index.name = "Date"
    df = df.loc[~df.index.duplicated(keep="last")].sort_index()
    for col in OHLCV:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # 缺值或不合理價格必須報錯，避免悄悄刪掉交易日後仍計算均線。
    finite = df.map(lambda v: pd.notna(v) and isfinite(float(v)))
    if not finite.all().all():
        raise DataError("資料來源含缺值或非有限數值，請重新查詢。")
    bad_price = (df[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)
    bad_range = (
        (df["High"] < df[["Open", "Close", "Low"]].max(axis=1))
        | (df["Low"] > df[["Open", "Close", "High"]].min(axis=1))
    )
    if bad_price.any() or bad_range.any() or (df["Volume"] < 0).any():
        raise DataError("資料來源含不合理的價格區間或成交量，請重新查詢。")
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """先用完整歷史計算，再裁切畫面，讓短區間也有足夠均線資料。"""
    result = df.copy()
    for window in (5, 20, 60):
        result[f"MA{window}"] = result["Close"].rolling(window, min_periods=window).mean()
    return result


def select_period(df: pd.DataFrame, label: str) -> pd.DataFrame:
    if label not in PERIODS:
        raise DataError("不支援的顯示期間。")
    start = df.index[-1] - pd.DateOffset(months=PERIODS[label])
    return df.loc[df.index >= start].copy()


def latest_summary(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    previous = float(df.iloc[-2]["Close"]) if len(df) >= 2 else None
    close = float(last["Close"])
    change = close - previous if previous is not None else None
    percent = change / previous * 100 if previous is not None else None
    return {"close": close, "change": change, "percent": percent,
            "volume": float(last["Volume"]), "high": float(last["High"]),
            "low": float(last["Low"]), "date": df.index[-1].strftime("%Y-%m-%d")}


def fetch_history(symbol: str) -> tuple[pd.DataFrame, str]:
    """以未還原日線查詢；錯誤時絕不切換成示範資料。"""
    import yfinance as yf

    try:
        raw = yf.Ticker(symbol).history(
            period="5y", interval="1d", auto_adjust=False,
            actions=False, timeout=20, raise_errors=True,
        )
    except Exception as exc:
        raise DataError(
            "無法取得 Yahoo Finance 資料。請確認網路、代號及市場；"
            "若服務限流，請稍後重試。你也可以選擇「離線示範」練習。"
        ) from exc
    return clean_history(raw), datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")


def demo_history() -> pd.DataFrame:
    """固定亂數產生虛構資料；日期僅排除週末，不代表台股交易日曆。"""
    rng = random.Random(20261117)
    rows = []
    previous = 100.0
    dates = pd.bdate_range(end="2026-10-30", periods=800)
    for _ in dates:
        opening = round(previous * (1 + rng.uniform(-0.008, 0.008)), 2)
        close = round(opening * (1 + rng.uniform(-0.024, 0.026)), 2)
        high = round(max(opening, close) * (1 + rng.uniform(0.001, 0.012)), 2)
        low = round(min(opening, close) * (1 - rng.uniform(0.001, 0.012)), 2)
        rows.append([opening, high, low, close, rng.randint(400, 6000) * 1000])
        previous = close
    return clean_history(pd.DataFrame(rows, columns=OHLCV, index=dates))


def export_csv(df: pd.DataFrame, symbol: str, source: str) -> bytes:
    """保留來源與示範標記；BOM 讓 Excel 正確辨識中文。"""
    result = df.copy()
    result.index = result.index.strftime("%Y-%m-%d")
    result.index.name = "日期"
    result.insert(0, "代號", symbol)
    result.insert(1, "資料來源", source)
    result = result.rename(columns={"Open": "開盤", "High": "最高", "Low": "最低",
                                    "Close": "收盤", "Volume": "成交量_股"})
    return result.to_csv(float_format="%.4f").encode("utf-8-sig")
