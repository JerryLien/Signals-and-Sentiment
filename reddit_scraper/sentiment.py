"""Reddit 情緒分析 — 結合 upvote ratio + 關鍵字情緒判斷。

Reddit 沒有 PTT 的推/噓系統，情緒來源不同：
1. upvote_ratio — 文章本身的社群認同度
2. post score (upvotes - downvotes) — 曝光度
3. 關鍵字情緒 — 標題 + 內文中的看多/看空用語
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from reddit_scraper.scraper import RedditPost

# WSB / Reddit 投資版常見的看多/看空關鍵字
_BULLISH_KEYWORDS: list[str] = [
    "bullish",
    "calls",
    "long",
    "buy",
    "moon",
    "to the moon",
    "rocket",
    "diamond hands",
    "tendies",
    "undervalued",
    "breakout",
    "squeeze",
    "gamma squeeze",
    "short squeeze",
    "going up",
    "buy the dip",
    "btfd",
    "loading up",
    "all in",
    "yolo",
    "lets go",
    "lfg",
]

_BEARISH_KEYWORDS: list[str] = [
    "bearish",
    "puts",
    "short",
    "sell",
    "crash",
    "dump",
    "overvalued",
    "bubble",
    "bag holder",
    "bagholding",
    "loss porn",
    "guh",
    "rip",
    "dead cat bounce",
    "going down",
    "top is in",
    "exit",
    "taking profits",
    "rug pull",
    "scam",
    "ponzi",
]

_BULLISH_RE = re.compile(
    "|".join(re.escape(kw) for kw in _BULLISH_KEYWORDS),
    re.IGNORECASE,
)
_BEARISH_RE = re.compile(
    "|".join(re.escape(kw) for kw in _BEARISH_KEYWORDS),
    re.IGNORECASE,
)


@dataclass
class RedditSentimentResult:
    """單篇 Reddit 文章的情緒分析結果。"""

    title: str
    url: str
    subreddit: str
    score: float  # 綜合情緒分數
    label: str  # bullish / bearish / neutral
    upvote_ratio: float  # Reddit 原始 upvote ratio
    post_score: int  # upvotes - downvotes
    bullish_hits: int  # 看多關鍵字命中數
    bearish_hits: int  # 看空關鍵字命中數


class RedditSentimentScorer:
    """Reddit 文章情緒計分器。

    計分公式:
        score = (upvote_ratio - 0.5) * 10        # [-5, +5] 範圍
              + bullish_keyword_count * 1.0
              + bearish_keyword_count * -1.0
              + comment_sentiment_bonus          # 如果有抓留言

    Parameters
    ----------
    bullish_threshold : float
        分數 >= 此值判定為 bullish。
    bearish_threshold : float
        分數 <= 此值判定為 bearish。
    """

    def __init__(
        self,
        bullish_threshold: float = 2.0,
        bearish_threshold: float = -2.0,
    ):
        self.bullish_threshold = bullish_threshold
        self.bearish_threshold = bearish_threshold

    def analyze_post(self, post: RedditPost) -> RedditSentimentResult:
        text = post.title + " " + post.selftext
        for c in post.comments:
            text += " " + c.body

        bullish_hits = len(_BULLISH_RE.findall(text))
        bearish_hits = len(_BEARISH_RE.findall(text))

        # upvote_ratio: 0.0~1.0，0.5 為中性
        ratio_score = (post.upvote_ratio - 0.5) * 10
        keyword_score = bullish_hits * 1.0 + bearish_hits * -1.0

        # 留言加成：高分留言的數量
        comment_bonus = 0.0
        if post.comments:
            positive_comments = sum(1 for c in post.comments if c.score > 5)
            negative_comments = sum(1 for c in post.comments if c.score < -2)
            comment_bonus = (positive_comments - negative_comments) * 0.5

        score = ratio_score + keyword_score + comment_bonus

        if score >= self.bullish_threshold:
            label = "bullish"
        elif score <= self.bearish_threshold:
            label = "bearish"
        else:
            label = "neutral"

        return RedditSentimentResult(
            title=post.title,
            url=post.url,
            subreddit=post.subreddit,
            score=round(score, 2),
            label=label,
            upvote_ratio=post.upvote_ratio,
            post_score=post.score,
            bullish_hits=bullish_hits,
            bearish_hits=bearish_hits,
        )

    def analyze_posts(self, posts: list[RedditPost]) -> list[RedditSentimentResult]:
        return [self.analyze_post(p) for p in posts]
