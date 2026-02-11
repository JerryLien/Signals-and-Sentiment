"""PTT 股板專有名詞 → 證券代碼對應 (Entity Mapping)。

類似 ICE 把 Reddit 上的 "Micky Mouse" 對應到 Disney ticker，
這裡把 PTT 鄉民常用的暱稱對應到台股證券代碼。

暱稱來源：
- data/aliases.json        — 靜態對應表（手動維護，版本控制）
- data/dynamic_aliases.json — 動態對應表（由 feed.py 自動產生）
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_STATIC_PATH = _DATA_DIR / "aliases.json"
_DYNAMIC_PATH = _DATA_DIR / "dynamic_aliases.json"

# 直接以數字代碼出現的 pattern，例如 "2330" 或 "2330.TW"
# 用 lookaround 取代 \b，因為 Python re 的 \b 把中文字視為 \w，
# 導致 "2317也在漲" 中的 2317 無法被抓到。
_TICKER_PATTERN = re.compile(r"(?<!\d)(\d{4,6})(?:\.TW)?(?!\d)")


def _load_json(path: Path) -> dict[str, list[str]]:
    """載入 JSON 暱稱檔，略過 _ 開頭的 metadata key。"""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


class EntityMapper:
    """將 PTT 文章中的股票暱稱對應到證券代碼。

    載入順序：static aliases → dynamic aliases → extra_aliases。
    後載入的會覆蓋前者，因此動態暱稱（如「股王」）能正確反映最新行情。

    Parameters
    ----------
    extra_aliases : dict, optional
        程式碼層級的額外對應，格式: {"暱稱": ("代碼", "名稱"), ...}。
    """

    def __init__(self, extra_aliases: dict[str, tuple[str, str]] | None = None):
        # 載入靜態 + 動態 JSON
        self.aliases: dict[str, tuple[str, str]] = {}
        for path in (_STATIC_PATH, _DYNAMIC_PATH):
            for alias, pair in _load_json(path).items():
                self.aliases[alias] = (pair[0], pair[1])

        if extra_aliases:
            self.aliases.update(extra_aliases)

        # 依暱稱長度降冪排序，避免短暱稱先 match 造成錯誤
        self._sorted_keys = sorted(self.aliases.keys(), key=len, reverse=True)

    def find_entities(self, text: str) -> list[dict[str, str]]:
        """從文字中找出所有可辨識的股票實體。

        Returns
        -------
        list of dict
            每個 dict 包含 ``ticker``, ``name``, ``matched`` 欄位。
        """
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

        # 2. 純數字代碼比對
        for match in _TICKER_PATTERN.finditer(text):
            ticker = match.group(1)
            if ticker not in found:
                found[ticker] = {
                    "ticker": ticker,
                    "name": "",
                    "matched": match.group(0),
                }

        return list(found.values())
