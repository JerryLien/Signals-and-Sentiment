"""PTT 股板專有名詞 → 證券代碼對應 (Entity Mapping)。

類似 ICE 把 Reddit 上的 "Micky Mouse" 對應到 Disney ticker，
這裡把 PTT 鄉民常用的暱稱對應到台股證券代碼。
"""

from __future__ import annotations

import re


# 台股常見暱稱對應表
# 格式: 暱稱 (小寫) -> (證券代碼, 公司名稱)
_DEFAULT_ALIASES: dict[str, tuple[str, str]] = {
    # 台積電
    "gg": ("2330", "台積電"),
    "台gg": ("2330", "台積電"),
    "神山": ("2330", "台積電"),
    "護國神山": ("2330", "台積電"),
    "tsmc": ("2330", "台積電"),
    "台積": ("2330", "台積電"),
    # 鴻海
    "郭董": ("2317", "鴻海"),
    "土城鵝": ("2317", "鴻海"),
    "海公公": ("2317", "鴻海"),
    "鴻海": ("2317", "鴻海"),
    "foxconn": ("2317", "鴻海"),
    # 聯發科
    "發哥": ("2454", "聯發科"),
    "mtk": ("2454", "聯發科"),
    "聯發科": ("2454", "聯發科"),
    # 大立光
    "股王": ("3008", "大立光"),
    "大立光": ("3008", "大立光"),
    # 中華電
    "中華電": ("2412", "中華電信"),
    "中華電信": ("2412", "中華電信"),
    # 台達電
    "台達電": ("2308", "台達電"),
    "台達": ("2308", "台達電"),
    "delta": ("2308", "台達電"),
    # 長榮
    "長榮": ("2603", "長榮"),
    "長榮海": ("2603", "長榮"),
    # 陽明
    "陽明": ("2609", "陽明"),
    "陽明海運": ("2609", "陽明"),
    # 萬海
    "萬海": ("2615", "萬海"),
    # 國巨
    "國巨": ("2327", "國巨"),
    # 廣達
    "廣達": ("2382", "廣達"),
    # 緯創
    "緯創": ("3231", "緯創"),
    # 英業達
    "英業達": ("2356", "英業達"),
    # 仁寶
    "仁寶": ("2324", "仁寶"),
    # 華碩
    "華碩": ("2357", "華碩"),
    # 宏碁
    "宏碁": ("2353", "宏碁"),
    # 聯電
    "聯電": ("2303", "聯電"),
    "umc": ("2303", "聯電"),
    # 日月光
    "日月光": ("3711", "日月光投控"),
    # 富邦金
    "富邦金": ("2881", "富邦金"),
    "富邦": ("2881", "富邦金"),
    # 國泰金
    "國泰金": ("2882", "國泰金"),
    "國泰": ("2882", "國泰金"),
    # 中信金
    "中信金": ("2891", "中信金"),
    "中信": ("2891", "中信金"),
    # 兆豐金
    "兆豐金": ("2886", "兆豐金"),
    "兆豐": ("2886", "兆豐金"),
    # 玉山金
    "玉山金": ("2884", "玉山金"),
    "玉山": ("2884", "玉山金"),
    # 大盤 / 指數
    "大盤": ("TAIEX", "加權指數"),
    "加權": ("TAIEX", "加權指數"),
    "台指": ("TX", "台指期"),
    "小台": ("MTX", "小型台指期"),
}

# 直接以數字代碼出現的 pattern，例如 "2330" 或 "2330.TW"
# 用 lookaround 取代 \b，因為 Python re 的 \b 把中文字視為 \w，
# 導致 "2317也在漲" 中的 2317 無法被抓到。
_TICKER_PATTERN = re.compile(r"(?<!\d)(\d{4,6})(?:\.TW)?(?!\d)")


class EntityMapper:
    """將 PTT 文章中的股票暱稱對應到證券代碼。

    Parameters
    ----------
    extra_aliases : dict, optional
        額外的暱稱對應表，格式同 _DEFAULT_ALIASES。
    """

    def __init__(self, extra_aliases: dict[str, tuple[str, str]] | None = None):
        self.aliases = dict(_DEFAULT_ALIASES)
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
