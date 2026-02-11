"""板塊輪動偵測 — 從 PTT 文章中識別當前最熱門的投資主題。

核心概念:
- 載入 data/sectors.json 定義的板塊/主題與對應關鍵字
- 統計每個主題在文章中被提及的頻率
- 排序產出「板塊熱度排行」，捕捉散戶資金關注方向的變化
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ptt_scraper.scraper import Post


_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_SECTORS_PATH = _DATA_DIR / "sectors.json"


@dataclass
class SectorHeat:
    """單一板塊/主題的熱度。"""

    sector: str
    mention_count: int
    matched_keywords: list[str] = field(default_factory=list)
    sample_titles: list[str] = field(default_factory=list)


@dataclass
class SectorReport:
    """板塊輪動報告。"""

    total_posts: int
    sectors: list[SectorHeat]

    @property
    def top_sector(self) -> str:
        return self.sectors[0].sector if self.sectors else ""


def _load_sectors() -> dict[str, dict]:
    """載入 sectors.json。"""
    if not _SECTORS_PATH.exists():
        return {}
    with open(_SECTORS_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


class SectorTracker:
    """追蹤 PTT 文章中的板塊/主題熱度。

    Parameters
    ----------
    extra_sectors : dict, optional
        額外的板塊定義，格式同 sectors.json。
    """

    def __init__(self, extra_sectors: dict[str, dict] | None = None):
        self.sectors = _load_sectors()
        if extra_sectors:
            self.sectors.update(extra_sectors)

        # 為每個板塊編譯 regex
        self._patterns: dict[str, re.Pattern] = {}
        for sector, cfg in self.sectors.items():
            keywords = cfg.get("keywords", [])
            if keywords:
                pattern = "|".join(re.escape(kw) for kw in keywords)
                self._patterns[sector] = re.compile(pattern, re.IGNORECASE)

    def analyze(self, posts: list[Post]) -> SectorReport:
        """分析一批文章的板塊熱度。"""
        heat_map: dict[str, SectorHeat] = {
            sector: SectorHeat(sector=sector, mention_count=0)
            for sector in self.sectors
        }

        for post in posts:
            text = post.title + " " + post.content
            for c in post.comments:
                text += " " + c.content

            for sector, pattern in self._patterns.items():
                matches = pattern.findall(text)
                if matches:
                    entry = heat_map[sector]
                    entry.mention_count += len(matches)
                    existing_lower = {k.lower() for k in entry.matched_keywords}
                    for m in set(matches):
                        if m.lower() not in existing_lower:
                            entry.matched_keywords.append(m)
                            existing_lower.add(m.lower())
                    if post.title not in entry.sample_titles and len(entry.sample_titles) < 3:
                        entry.sample_titles.append(post.title)

        # 按熱度降冪排序，過濾掉 mention_count == 0 的
        ranked = sorted(
            (h for h in heat_map.values() if h.mention_count > 0),
            key=lambda h: h.mention_count,
            reverse=True,
        )

        return SectorReport(total_posts=len(posts), sectors=ranked)
