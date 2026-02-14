"""Tests for ptt_scraper.sentiment module."""

import pytest

from ptt_scraper.scraper import Comment, Post
from ptt_scraper.sentiment import SentimentResult, SentimentScorer


def _make_post(title: str = "測試文章", comments: list[Comment] | None = None) -> Post:
    return Post(
        title=title,
        url="https://www.ptt.cc/bbs/Stock/M.123.A.456.html",
        author="testuser",
        date="1/01",
        content="測試內文",
        comments=comments or [],
    )


class TestSentimentScorer:
    def test_empty_comments_returns_neutral(self):
        scorer = SentimentScorer()
        post = _make_post(comments=[])
        result = scorer.analyze_post(post)
        assert result.label == "neutral"
        assert result.score == 0.0
        assert result.push_count == 0
        assert result.boo_count == 0
        assert result.arrow_count == 0

    def test_all_pushes_returns_bullish(self):
        scorer = SentimentScorer()
        comments = [Comment(tag="推", user=f"user{i}", content="推") for i in range(5)]
        post = _make_post(comments=comments)
        result = scorer.analyze_post(post)
        assert result.push_count == 5
        assert result.boo_count == 0
        assert result.score == 5.0  # 5 * 1.0
        assert result.label == "bullish"

    def test_all_boos_returns_bearish(self):
        scorer = SentimentScorer()
        comments = [Comment(tag="噓", user=f"user{i}", content="噓") for i in range(3)]
        post = _make_post(comments=comments)
        result = scorer.analyze_post(post)
        assert result.push_count == 0
        assert result.boo_count == 3
        assert result.score == -4.5  # 3 * -1.5
        assert result.label == "bearish"

    def test_arrows_are_neutral(self):
        scorer = SentimentScorer()
        comments = [Comment(tag="→", user="user1", content="補充一下")]
        post = _make_post(comments=comments)
        result = scorer.analyze_post(post)
        assert result.arrow_count == 1
        assert result.score == 0.0  # 1 * 0.0
        assert result.label == "neutral"

    def test_mixed_comments(self):
        scorer = SentimentScorer()
        comments = [
            Comment(tag="推", user="user1", content="推"),
            Comment(tag="推", user="user2", content="推"),
            Comment(tag="噓", user="user3", content="噓"),
            Comment(tag="→", user="user4", content="觀望"),
        ]
        post = _make_post(comments=comments)
        result = scorer.analyze_post(post)
        assert result.push_count == 2
        assert result.boo_count == 1
        assert result.arrow_count == 1
        expected_score = 2 * 1.0 + 1 * (-1.5) + 1 * 0.0  # 0.5
        assert result.score == pytest.approx(expected_score)
        assert result.label == "neutral"

    def test_custom_thresholds(self):
        scorer = SentimentScorer(bullish_threshold=0.5, bearish_threshold=-0.5)
        comments = [Comment(tag="推", user="user1", content="推")]
        post = _make_post(comments=comments)
        result = scorer.analyze_post(post)
        assert result.score == 1.0
        assert result.label == "bullish"

    def test_custom_weights(self):
        scorer = SentimentScorer(push_weight=2.0, boo_weight=-3.0)
        comments = [
            Comment(tag="推", user="user1", content="推"),
            Comment(tag="噓", user="user2", content="噓"),
        ]
        post = _make_post(comments=comments)
        result = scorer.analyze_post(post)
        expected = 2.0 + (-3.0)  # -1.0
        assert result.score == pytest.approx(expected)

    def test_analyze_posts_batch(self):
        scorer = SentimentScorer()
        posts = [_make_post(title=f"文章{i}") for i in range(3)]
        results = scorer.analyze_posts(posts)
        assert len(results) == 3
        assert all(isinstance(r, SentimentResult) for r in results)

    def test_sentiment_result_total_comments(self):
        result = SentimentResult(
            title="test",
            url="http://test",
            push_count=3,
            boo_count=2,
            arrow_count=5,
            score=0.0,
            label="neutral",
        )
        assert result.total_comments == 10

    def test_score_comments_method(self):
        scorer = SentimentScorer()
        comments = [
            Comment(tag="推", user="a", content=""),
            Comment(tag="噓", user="b", content=""),
            Comment(tag="→", user="c", content=""),
        ]
        push, boo, arrow, score = scorer.score_comments(comments)
        assert push == 1
        assert boo == 1
        assert arrow == 1
        assert score == pytest.approx(1.0 + (-1.5) + 0.0)
