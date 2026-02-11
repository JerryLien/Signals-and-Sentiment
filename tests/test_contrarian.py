"""Tests for ptt_scraper.contrarian module."""

from ptt_scraper.contrarian import (
    ContrarianSignal,
    ContrarianSummary,
    detect_contrarian,
    summarize_contrarian,
)
from ptt_scraper.scraper import Comment, Post


def _make_post(
    title: str = "測試",
    content: str = "",
    comments: list[Comment] | None = None,
) -> Post:
    return Post(
        title=title,
        url="https://www.ptt.cc/bbs/Stock/M.123.A.456.html",
        author="test",
        date="1/01",
        content=content,
        comments=comments or [],
    )


class TestDetectContrarian:
    def test_capitulation_keywords(self):
        post = _make_post(
            title="畢業了",
            content="賠光了所有積蓄，認賠出場",
        )
        signal = detect_contrarian(post)
        assert len(signal.capitulation_hits) >= 2
        assert signal.is_capitulation

    def test_euphoria_keywords(self):
        post = _make_post(
            title="要財富自由了",
            content="歐印梭哈，睏霸數錢",
        )
        signal = detect_contrarian(post)
        assert len(signal.euphoria_hits) >= 2
        assert signal.is_euphoria

    def test_no_signal(self):
        post = _make_post(title="法說會重點整理", content="營收年增10%")
        signal = detect_contrarian(post)
        assert not signal.is_capitulation
        assert not signal.is_euphoria
        assert signal.signal_type == "none"

    def test_single_keyword_not_enough(self):
        post = _make_post(title="畢業的感覺", content="今天股票表現不錯")
        signal = detect_contrarian(post)
        # Only 1 hit — not enough to classify as capitulation (needs >= 2)
        assert not signal.is_capitulation

    def test_comments_included(self):
        post = _make_post(
            title="今天行情",
            content="大盤漲了",
            comments=[
                Comment(tag="推", user="u1", content="畢業了啦"),
                Comment(tag="推", user="u2", content="賠光光"),
            ],
        )
        signal = detect_contrarian(post)
        assert len(signal.capitulation_hits) >= 2

    def test_signal_type_property(self):
        signal = ContrarianSignal(
            title="test",
            url="http://test",
            capitulation_hits=["畢業", "賠光"],
            euphoria_hits=[],
        )
        assert signal.signal_type == "capitulation"

        signal2 = ContrarianSignal(
            title="test",
            url="http://test",
            capitulation_hits=[],
            euphoria_hits=["歐印", "梭哈"],
        )
        assert signal2.signal_type == "euphoria"


class TestSummarizeContrarian:
    def test_empty_posts(self):
        summary = summarize_contrarian([])
        assert summary.total_posts == 0
        assert summary.capitulation_count == 0
        assert summary.euphoria_count == 0
        assert summary.market_signal == "neutral"

    def test_neutral_market(self):
        posts = [_make_post(title=f"正常文章{i}", content="法說會") for i in range(10)]
        summary = summarize_contrarian(posts)
        assert summary.market_signal == "neutral"
        assert summary.capitulation_ratio == 0.0
        assert summary.euphoria_ratio == 0.0

    def test_extreme_fear_signal(self):
        # 20% capitulation posts → extreme_fear
        capitulation_posts = [
            _make_post(title=f"畢業了{i}", content="賠光認賠斷頭") for i in range(4)
        ]
        normal_posts = [_make_post(title=f"正常{i}", content="看看後續發展") for i in range(16)]
        summary = summarize_contrarian(capitulation_posts + normal_posts)
        assert summary.total_posts == 20
        assert summary.capitulation_count == 4
        assert summary.capitulation_ratio >= 0.15
        assert summary.market_signal == "extreme_fear"

    def test_extreme_greed_signal(self):
        euphoria_posts = [
            _make_post(title=f"歐印{i}", content="梭哈睏霸數錢財富自由") for i in range(4)
        ]
        normal_posts = [_make_post(title=f"正常{i}", content="觀望中") for i in range(16)]
        summary = summarize_contrarian(euphoria_posts + normal_posts)
        assert summary.euphoria_count == 4
        assert summary.market_signal == "extreme_greed"

    def test_summary_ratios(self):
        summary = ContrarianSummary(
            total_posts=100,
            capitulation_count=5,
            euphoria_count=3,
            capitulation_posts=[],
            euphoria_posts=[],
        )
        assert summary.capitulation_ratio == 0.05
        assert summary.euphoria_ratio == 0.03

    def test_zero_total_posts_no_division_error(self):
        summary = ContrarianSummary(
            total_posts=0,
            capitulation_count=0,
            euphoria_count=0,
            capitulation_posts=[],
            euphoria_posts=[],
        )
        assert summary.capitulation_ratio == 0.0
        assert summary.euphoria_ratio == 0.0
