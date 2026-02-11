"""動態暱稱更新 — 從 TWSE / TPEX 公開 API 取得即時行情，產生動態對應表。

「股王」、「股后」這類暱稱會隨市場價格變動，不適合 hardcode。
本模組定期查詢交易所 API，自動寫入 data/dynamic_aliases.json。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# TWSE / TPEX Open Data API（免費、免 API key）
TWSE_QUOTES_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_QUOTES_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DYNAMIC_ALIASES_PATH = _DATA_DIR / "dynamic_aliases.json"

# UTC+8 台灣時區
_TW_TZ = timezone(timedelta(hours=8))


def _parse_price(raw: str) -> float | None:
    """安全解析價格字串，處理逗號與非數字。"""
    try:
        return float(raw.replace(",", ""))
    except (ValueError, TypeError, AttributeError):
        return None


def _fetch_twse_quotes() -> list[dict]:
    """取得上市股票收盤行情。回傳 [{code, name, close}, ...]。"""
    resp = requests.get(TWSE_QUOTES_URL, timeout=30)
    resp.raise_for_status()
    results = []
    for row in resp.json():
        code = row.get("Code", "")
        name = row.get("Name", "")
        close = _parse_price(row.get("ClosingPrice", ""))
        if code and close is not None:
            results.append({"code": code, "name": name, "close": close})
    return results


def _fetch_tpex_quotes() -> list[dict]:
    """取得上櫃股票收盤行情。回傳 [{code, name, close}, ...]。"""
    resp = requests.get(TPEX_QUOTES_URL, timeout=30)
    resp.raise_for_status()
    results = []
    for row in resp.json():
        code = row.get("SecuritiesCompanyCode", "")
        name = row.get("CompanyName", "")
        close = _parse_price(row.get("Close", ""))
        if code and close is not None:
            results.append({"code": code, "name": name, "close": close})
    return results


def compute_dynamic_aliases() -> dict[str, list[str]]:
    """查詢 TWSE + TPEX，計算動態暱稱對應表。

    目前支援的動態暱稱：
    - 股王：全市場（上市 + 上櫃）收盤價最高的股票
    - 股后：全市場收盤價第二高的股票

    Returns
    -------
    dict
        格式同 aliases.json: {"暱稱": ["代碼", "名稱"], ...}
    """
    all_quotes: list[dict] = []

    try:
        all_quotes.extend(_fetch_twse_quotes())
    except requests.RequestException as exc:
        logger.warning("無法取得 TWSE 行情: %s", exc)

    try:
        all_quotes.extend(_fetch_tpex_quotes())
    except requests.RequestException as exc:
        logger.warning("無法取得 TPEX 行情: %s", exc)

    if not all_quotes:
        logger.warning("無法取得任何行情資料，動態暱稱未更新。")
        return {}

    # 依收盤價降冪排序
    all_quotes.sort(key=lambda q: q["close"], reverse=True)

    aliases: dict[str, list[str]] = {}

    if len(all_quotes) >= 1:
        top = all_quotes[0]
        aliases["股王"] = [top["code"], top["name"]]

    if len(all_quotes) >= 2:
        second = all_quotes[1]
        aliases["股后"] = [second["code"], second["name"]]

    return aliases


def update_dynamic_aliases() -> Path:
    """計算動態暱稱並寫入 data/dynamic_aliases.json。

    Returns
    -------
    Path
        寫入的檔案路徑。
    """
    aliases = compute_dynamic_aliases()

    now = datetime.now(tz=_TW_TZ).isoformat(timespec="seconds")
    payload = {
        "_updated_at": now,
        "_comment": "此檔案由 feed.py 自動產生，請勿手動編輯。",
        **aliases,
    }

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    DYNAMIC_ALIASES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("動態暱稱已更新 → %s", DYNAMIC_ALIASES_PATH)
    for name, (code, company) in aliases.items():
        logger.info("  %s → %s %s", name, code, company)

    return DYNAMIC_ALIASES_PATH
