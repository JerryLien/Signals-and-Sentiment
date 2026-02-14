"""Reddit 美股/加密貨幣實體辨識。

辨識方式：
1. 暱稱比對 (data/reddit_aliases.json) — "su bae" → AMD
2. $TICKER 語法 — Reddit 常見的 "$NVDA", "$BTC" 格式
3. 全大寫 ticker — 2~5 字母全大寫且不在常見英文字排除表中
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_ALIASES_PATH = _DATA_DIR / "reddit_aliases.json"

# $TICKER 語法，Reddit 特有
_DOLLAR_TICKER = re.compile(r"\$([A-Z]{1,5})\b")

# 全大寫 2~5 字母 (可能是 ticker)
_BARE_TICKER = re.compile(r"\b([A-Z]{2,5})\b")

# 常見英文字排除表 — 避免把 "I", "AM", "THE" 等誤判為 ticker
_COMMON_WORDS: set[str] = {
    "I",
    "A",
    "AM",
    "AN",
    "AS",
    "AT",
    "BE",
    "BY",
    "DD",
    "DO",
    "GO",
    "IF",
    "IN",
    "IS",
    "IT",
    "ME",
    "MY",
    "NO",
    "OF",
    "OK",
    "ON",
    "OR",
    "SO",
    "TO",
    "UP",
    "US",
    "WE",
    "ALL",
    "AND",
    "ANY",
    "ARE",
    "BUT",
    "CAN",
    "DAY",
    "DID",
    "FOR",
    "GET",
    "GOT",
    "HAS",
    "HAD",
    "HER",
    "HIM",
    "HIS",
    "HOW",
    "ITS",
    "LET",
    "LOT",
    "MAY",
    "NEW",
    "NOT",
    "NOW",
    "OLD",
    "ONE",
    "OUR",
    "OUT",
    "OWN",
    "PUT",
    "RUN",
    "SAY",
    "SEE",
    "SET",
    "SHE",
    "THE",
    "TOO",
    "TWO",
    "USE",
    "WAY",
    "WHO",
    "WHY",
    "WIN",
    "WON",
    "YET",
    "YOU",
    "ALSO",
    "BACK",
    "BEEN",
    "CALL",
    "COME",
    "DOES",
    "DOWN",
    "EACH",
    "EVEN",
    "FIND",
    "FIRST",
    "FROM",
    "GAVE",
    "GOOD",
    "HAVE",
    "HERE",
    "HIGH",
    "HOLD",
    "HOPE",
    "JUST",
    "KEEP",
    "KNOW",
    "LAST",
    "LIKE",
    "LONG",
    "LOOK",
    "MADE",
    "MAKE",
    "MANY",
    "MORE",
    "MOST",
    "MUCH",
    "MUST",
    "NEED",
    "NEXT",
    "ONLY",
    "OPEN",
    "OVER",
    "PART",
    "PAST",
    "PLAY",
    "SAME",
    "SAID",
    "SELL",
    "SOME",
    "SURE",
    "TAKE",
    "TELL",
    "THAN",
    "THAT",
    "THEM",
    "THEN",
    "THEY",
    "THIS",
    "TIME",
    "VERY",
    "WANT",
    "WELL",
    "WENT",
    "WERE",
    "WHAT",
    "WHEN",
    "WILL",
    "WITH",
    "WORK",
    "YEAR",
    "YOUR",
    "ABOUT",
    "AFTER",
    "BEING",
    "COULD",
    "EVERY",
    "GOING",
    "GREAT",
    "NEVER",
    "OTHER",
    "PLACE",
    "RIGHT",
    "SHALL",
    "SINCE",
    "STILL",
    "THEIR",
    "THERE",
    "THESE",
    "THING",
    "THINK",
    "THOSE",
    "UNTIL",
    "WATCH",
    "WHICH",
    "WHILE",
    "WORLD",
    "WOULD",
    # Reddit/WSB 常見非 ticker 縮寫
    "IMO",
    "IMHO",
    "TBH",
    "YOLO",
    "FOMO",
    "HODL",
    "LMAO",
    "ROFL",
    "TLDR",
    "WSB",
    "SEC",
    "NYSE",
    "IPO",
    "CEO",
    "CFO",
    "CTO",
    "ETF",
    "GDP",
    "CPI",
    "ATH",
    "ATL",
    "OTC",
    "NFT",
    "DAO",
    "DCA",
    "RSI",
    "EPS",
    "PE",
    "ROI",
    "APY",
    "APR",
    "EDIT",
    "UPDATE",
    "LINK",
    "POST",
    "PUMP",
    "DUMP",
    "MOON",
    "BEAR",
    "BULL",
    "SHORT",
}


def _load_aliases() -> dict[str, list[str]]:
    if not _ALIASES_PATH.exists():
        return {}
    with open(_ALIASES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


class RedditEntityMapper:
    """辨識 Reddit 文章中提及的美股/加密貨幣。

    Parameters
    ----------
    extra_aliases : dict, optional
        額外的暱稱對應。
    """

    def __init__(self, extra_aliases: dict[str, tuple[str, str]] | None = None):
        self.aliases: dict[str, tuple[str, str]] = {}
        for alias, pair in _load_aliases().items():
            self.aliases[alias] = (pair[0], pair[1])
        if extra_aliases:
            self.aliases.update(extra_aliases)
        self._sorted_keys = sorted(self.aliases.keys(), key=len, reverse=True)

    def find_entities(self, text: str) -> list[dict[str, str]]:
        """從文字中找出所有可辨識的股票/加密貨幣實體。"""
        found: dict[str, dict[str, str]] = {}
        lower_text = text.lower()

        # 1. 暱稱比對
        for alias in self._sorted_keys:
            if alias in lower_text:
                ticker, name = self.aliases[alias]
                if ticker not in found:
                    found[ticker] = {
                        "ticker": ticker,
                        "name": name,
                        "matched": alias,
                    }

        # 2. $TICKER 語法（最可靠）
        for match in _DOLLAR_TICKER.finditer(text):
            ticker = match.group(1)
            if ticker not in found:
                found[ticker] = {
                    "ticker": ticker,
                    "name": "",
                    "matched": f"${ticker}",
                }

        # 3. 全大寫 bare ticker（過濾常見英文字）
        for match in _BARE_TICKER.finditer(text):
            ticker = match.group(1)
            if ticker not in found and ticker not in _COMMON_WORDS:
                found[ticker] = {
                    "ticker": ticker,
                    "name": "",
                    "matched": ticker,
                }

        return list(found.values())
