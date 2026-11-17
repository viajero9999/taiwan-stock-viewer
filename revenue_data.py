"""月營收查詢與計算。金額統一為新台幣元；索引使用所屬年月。"""
from __future__ import annotations

from datetime import datetime
from math import isfinite, sin, pi
import random
import re

import pandas as pd
import requests

from stock_data import DataError, TAIPEI

API_URL = "https://api.finmindtrade.com/api/v4/data"
REVENUE_PERIODS = {"近 6 個月": 6, "近 12 個月": 12, "近 24 個月": 24, "近 36 個月": 36}


def normalize_company_code(value: str) -> str:
    value = value.strip().upper()
    if value.endswith(".TWO") or value.endswith(".TW"):
        value = value.rsplit(".", 1)[0]
    if not re.fullmatch(r"[0-9]{4,6}", value):
        raise DataError("請輸入公司股票代號，例如 2330、2317、6488。")
    if value.startswith("0"):
        raise DataError("ETF／基金沒有公司月營收，請改查公司股票，例如 2330。")
    return value


def clean_revenue(rows: list[dict], code: str) -> pd.DataFrame:
    """不把 date 或 create_time 當作營收月份或正式公告日期。"""
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise DataError("營收來源的資料格式不正確，請稍後重試。")
    if not rows:
        raise DataError("查無公司月營收。請確認公司代號；ETF 不適用，亦可能尚未公告或來源尚未更新。")
    raw = pd.DataFrame(rows)
    required = {"stock_id", "revenue_year", "revenue_month", "revenue"}
    if not required.issubset(raw.columns):
        raise DataError("營收來源缺少必要欄位，請稍後重試。")
    if not raw["stock_id"].astype(str).eq(code).all():
        raise DataError("來源傳回的公司代號不符，已停止顯示，請重新查詢。")
    for col in ("revenue_year", "revenue_month", "revenue"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
        if not raw[col].map(lambda v: pd.notna(v) and isfinite(float(v))).all():
            raise DataError("營收資料含缺值或無效數值，請重新查詢。")
    year, month = raw["revenue_year"], raw["revenue_month"]
    if not (year.between(1900, 2200) & year.mod(1).eq(0)
            & month.between(1, 12) & month.mod(1).eq(0)).all():
        raise DataError("來源的營收年月不正確。")
    index = pd.PeriodIndex([f"{int(y):04d}-{int(m):02d}" for y, m in zip(year, month)], freq="M")
    result = pd.DataFrame({"Revenue": raw["revenue"].to_numpy()}, index=index)
    result.index.name = "Month"
    if (result.groupby(level=0)["Revenue"].nunique() > 1).any():
        raise DataError("同一月份出現不同營收數值，請重新查詢或核對公司公告。")
    result = result.loc[~result.index.duplicated(keep="last")].sort_index()
    # 缺月留空，不能用「前一筆」假裝前月或去年同月。
    months = pd.period_range(result.index[0], result.index[-1], freq="M", name="Month")
    return result.reindex(months)


def calculate_revenue(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    revenue = result["Revenue"]
    previous_month, previous_year = revenue.shift(1), revenue.shift(12)
    result["PreviousYear"] = previous_year
    result["MoM"] = (revenue - previous_month) / previous_month.where(previous_month > 0) * 100
    result["YoY"] = (revenue - previous_year) / previous_year.where(previous_year > 0) * 100
    result["YTD"] = float("nan")
    result["YTDYoY"] = float("nan")
    for period in result.index:
        current = pd.period_range(f"{period.year}-01", period, freq="M")
        values = revenue.reindex(current)
        if values.notna().all():
            total = values.sum()
            result.loc[period, "YTD"] = total
            prior = revenue.reindex(current - 12)
            if prior.notna().all() and prior.sum() > 0:
                result.loc[period, "YTDYoY"] = (total - prior.sum()) / prior.sum() * 100
    return result


def select_revenue_period(df: pd.DataFrame, months: int) -> pd.DataFrame:
    if months not in REVENUE_PERIODS.values():
        raise DataError("不支援的營收顯示期間。")
    return df.loc[df.index >= df.index[-1] - (months - 1)].copy()


def fetch_revenue(code: str, token: str = "") -> tuple[pd.DataFrame, str]:
    code = normalize_company_code(code)
    now = datetime.now(TAIPEI)
    start = (pd.Timestamp(now.date()).replace(day=1) - pd.DateOffset(months=60)).date().isoformat()
    params = {"dataset": "TaiwanStockMonthRevenue", "data_id": code, "start_date": start}
    headers = {"Authorization": f"Bearer {token.strip()}"} if token.strip() else {}
    try:
        response = requests.get(API_URL, params=params, headers=headers, timeout=(10, 25))
        if response.status_code in (402, 429):
            raise DataError("營收查詢額度已用完或請求過於頻繁，請稍後重試；亦可在進階設定填入自己的 FinMind Token。")
        if response.status_code in (401, 403):
            raise DataError("營收來源拒絕存取，請確認 FinMind Token／權限，或清除 Token 後重試。")
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        if isinstance(exc, DataError):
            raise
        raise DataError("無法取得月營收，請檢查網路或稍後重試；不會自動切換成示範資料。") from exc
    if not isinstance(payload, dict):
        raise DataError("營收來源回傳格式不正確，請稍後重試。")
    if payload.get("status") in (402, 429):
        raise DataError("營收查詢額度已用完或請求過於頻繁，請稍後重試。")
    if payload.get("status") != 200:
        raise DataError("營收來源暫時無法提供資料，請確認代號、Token 或稍後重試。")
    frame = clean_revenue(payload.get("data"), code)
    if frame.index[-1] >= pd.Period(now.date(), freq="M"):
        raise DataError("來源包含尚未結束月份的月營收，請稍後重試或核對公司公告。")
    return frame, datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")


def demo_revenue() -> pd.DataFrame:
    rng = random.Random(20261117)
    rows = []
    for i, period in enumerate(pd.period_range("2021-01", "2026-10", freq="M")):
        amount = int(80_000_000 * (1 + 0.007 * i) * (1 + 0.15 * sin(period.month * pi / 6))
                     * rng.uniform(0.94, 1.06))
        rows.append({"stock_id": "DEMO", "revenue_year": period.year,
                     "revenue_month": period.month, "revenue": amount})
    return clean_revenue(rows, "DEMO")


def revenue_csv(df: pd.DataFrame, code: str, source: str) -> bytes:
    table = df.copy()
    table.index = table.index.astype(str)
    table.index.name = "營收月份"
    table.insert(0, "公司代號", code)
    table.insert(1, "資料來源", source)
    table = table.rename(columns={"Revenue": "月營收_新台幣元", "PreviousYear": "去年同月營收_新台幣元",
                                  "MoM": "月增率_%", "YoY": "年增率_%",
                                  "YTD": "當年累計營收_新台幣元", "YTDYoY": "累計年增率_%"})
    return table.to_csv(float_format="%.4f").encode("utf-8-sig")
