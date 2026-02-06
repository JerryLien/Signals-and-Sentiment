"""推文情緒分析 — 根據推/噓/→ 計算情緒分數。"""

from __future__ import annotations

from dataclasses import dataclass

from ptt_scraper.config import ARROW_WEIGHT, BOO_WEIGHT, PUSH_WEIGHT
from ptt_scraper.scraper import Comment, Post


@dataclass
class SentimentResult:
    """單篇文章的情緒分析結果。"""

    title: str
    url: str
    push_count: int
    boo_count: int
    arrow_count: int
    score: float
    label: str  # bullish / bearish / neutral

    @property
    def total_comments(self) -> int:
        return self.push_count + self.boo_count + self.arrow_count


class SentimentScorer:
    """根據 PTT 推文的推/噓/→ 標籤計算情緒分數。

    Parameters
    ----------
    push_weight : float
        「推」的權重，預設 1.0。
    boo_weight : float
        「噓」的權重，預設 -1.5（噓在股板通常更有意義）。
    arrow_weight : float
        「→」的權重，預設 0.0（中性補充）。
    bullish_threshold : float
        分數 >= 此值判定為 bullish。
    bearish_threshold : float
        分數 <= 此值判定為 bearish。
    """

    def __init__(
        self,
        push_weight: float = PUSH_WEIGHT,
        boo_weight: float = BOO_WEIGHT,
        arrow_weight: float = ARROW_WEIGHT,
        bullish_threshold: float = 2.0,
        bearish_threshold: float = -2.0,
    ):
        self.push_weight = push_weight
        self.boo_weight = boo_weight
        self.arrow_weight = arrow_weight
        self.bullish_threshold = bullish_threshold
        self.bearish_threshold = bearish_threshold

    def score_comments(self, comments: list[Comment]) -> tuple[int, int, int, float]:
        """計算推文的推/噓/→ 數量與加權分數。"""
        push = boo = arrow = 0
        for c in comments:
            if c.tag == "推":
                push += 1
            elif c.tag == "噓":
                boo += 1
            else:
                arrow += 1

        score = (
            push * self.push_weight
            + boo * self.boo_weight
            + arrow * self.arrow_weight
        )
        return push, boo, arrow, score

    def classify(self, score: float) -> str:
        if score >= self.bullish_threshold:
            return "bullish"
        elif score <= self.bearish_threshold:
            return "bearish"
        return "neutral"

    def analyze_post(self, post: Post) -> SentimentResult:
        """分析單篇文章的情緒。"""
        push, boo, arrow, score = self.score_comments(post.comments)
        return SentimentResult(
            title=post.title,
            url=post.url,
            push_count=push,
            boo_count=boo,
            arrow_count=arrow,
            score=score,
            label=self.classify(score),
        )

    def analyze_posts(self, posts: list[Post]) -> list[SentimentResult]:
        """批次分析多篇文章。"""
        return [self.analyze_post(p) for p in posts]
