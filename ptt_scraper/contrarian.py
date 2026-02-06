"""反指標偵測 — 偵測 PTT 股板「畢業文」與「歐印文」，量化市場恐慌 / 過熱。

策略邏輯:
- 「畢業文指數」飆高 → 散戶極度恐慌 → 潛在做多訊號（反指標）
- 「歐印文指數」飆高 → 散戶極度樂觀 → 潛在過熱訊號（反指標）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ptt_scraper.scraper import Post


# ------------------------------------------------------------------
# 關鍵字集合 — 可擴充
# ------------------------------------------------------------------

# 畢業 / 投降 (Capitulation) 相關關鍵字
CAPITULATION_KEYWORDS: list[str] = [
    "畢業", "賠光", "認賠", "出場", "慘賠", "斷頭",
    "融資追繳", "違約交割", "砍在阿呆谷", "停損",
    "血流成河", "套牢", "套到天荒地老", "心態炸裂",
    "不玩了", "刪app", "解套無望", "腰斬再腰斬",
    "住套房", "畢業典禮",
]

# 歐印 / 過度樂觀 (Euphoria) 相關關鍵字
EUPHORIA_KEYWORDS: list[str] = [
    "歐印", "all in", "allin", "梭哈", "睏霸數錢",
    "財富自由", "上車", "衝了", "噴到外太空",
    "要起飛了", "多軍集合", "無腦多", "躺著賺",
    "穩賺不賠", "開香檳", "提早退休", "信仰",
    "鑽石手", "diamond hand",
]

# 編譯成 regex（忽略大小寫）
_CAPITULATION_RE = re.compile(
    "|".join(re.escape(kw) for kw in CAPITULATION_KEYWORDS),
    re.IGNORECASE,
)
_EUPHORIA_RE = re.compile(
    "|".join(re.escape(kw) for kw in EUPHORIA_KEYWORDS),
    re.IGNORECASE,
)


@dataclass
class ContrarianSignal:
    """單篇文章的反指標訊號。"""

    title: str
    url: str
    capitulation_hits: list[str] = field(default_factory=list)
    euphoria_hits: list[str] = field(default_factory=list)

    @property
    def is_capitulation(self) -> bool:
        return len(self.capitulation_hits) >= 2

    @property
    def is_euphoria(self) -> bool:
        return len(self.euphoria_hits) >= 2

    @property
    def signal_type(self) -> str:
        if self.is_capitulation:
            return "capitulation"
        if self.is_euphoria:
            return "euphoria"
        return "none"


@dataclass
class ContrarianSummary:
    """一批文章的反指標彙總。"""

    total_posts: int
    capitulation_count: int
    euphoria_count: int
    capitulation_posts: list[ContrarianSignal]
    euphoria_posts: list[ContrarianSignal]

    @property
    def capitulation_ratio(self) -> float:
        return self.capitulation_count / self.total_posts if self.total_posts else 0.0

    @property
    def euphoria_ratio(self) -> float:
        return self.euphoria_count / self.total_posts if self.total_posts else 0.0

    @property
    def market_signal(self) -> str:
        """根據比例給出市場訊號。"""
        if self.capitulation_ratio >= 0.15:
            return "extreme_fear"
        if self.euphoria_ratio >= 0.15:
            return "extreme_greed"
        if self.capitulation_ratio >= 0.08:
            return "fear"
        if self.euphoria_ratio >= 0.08:
            return "greed"
        return "neutral"


def detect_contrarian(post: Post) -> ContrarianSignal:
    """偵測單篇文章中的反指標關鍵字。"""
    text = post.title + " " + post.content
    # 也把推文納入（畢業文底下的推文常有額外的投降訊號）
    for c in post.comments:
        text += " " + c.content

    cap_hits = list({m.group() for m in _CAPITULATION_RE.finditer(text)})
    eup_hits = list({m.group() for m in _EUPHORIA_RE.finditer(text)})

    return ContrarianSignal(
        title=post.title,
        url=post.url,
        capitulation_hits=cap_hits,
        euphoria_hits=eup_hits,
    )


def summarize_contrarian(posts: list[Post]) -> ContrarianSummary:
    """批次分析一批文章，產生反指標彙總。"""
    signals = [detect_contrarian(p) for p in posts]

    cap_posts = [s for s in signals if s.is_capitulation]
    eup_posts = [s for s in signals if s.is_euphoria]

    return ContrarianSummary(
        total_posts=len(posts),
        capitulation_count=len(cap_posts),
        euphoria_count=len(eup_posts),
        capitulation_posts=cap_posts,
        euphoria_posts=eup_posts,
    )
