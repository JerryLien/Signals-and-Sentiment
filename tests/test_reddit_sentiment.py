"""Tests for reddit_scraper.sentiment module."""

import pytest

from reddit_scraper.scraper import RedditComment, RedditPost
from reddit_scraper.sentiment import RedditSentimentResult, RedditSentimentScorer


def _make_post(
    title: str = "Test post",
    selftext: str = "",
    upvote_ratio: float = 0.5,
    score: int = 1,
    comments: list[RedditComment] | None = None,
) -> RedditPost:
    return RedditPost(
        title=title,
        url="https://www.reddit.com/r/wallstreetbets/comments/abc123/test/",
        subreddit="wallstreetbets",
        author="testuser",
        selftext=selftext,
        score=score,
        upvote_ratio=upvote_ratio,
        num_comments=0,
        comments=comments or [],
    )


class TestRedditSentimentScorer:
    def test_neutral_post(self):
        scorer = RedditSentimentScorer()
        post = _make_post(title="What happened today?", upvote_ratio=0.5)
        result = scorer.analyze_post(post)
        assert result.label == "neutral"
        assert result.bullish_hits == 0
        assert result.bearish_hits == 0

    def test_bullish_keywords(self):
        scorer = RedditSentimentScorer()
        post = _make_post(
            title="NVDA to the moon! Diamond hands!",
            selftext="This stock is bullish, buy the dip, calls printing",
            upvote_ratio=0.8,
        )
        result = scorer.analyze_post(post)
        assert result.bullish_hits >= 3
        assert result.label == "bullish"

    def test_bearish_keywords(self):
        scorer = RedditSentimentScorer()
        post = _make_post(
            title="Market crash incoming, sell everything",
            selftext="This is a bubble, bearish puts",
            upvote_ratio=0.3,
        )
        result = scorer.analyze_post(post)
        assert result.bearish_hits >= 3
        assert result.label == "bearish"

    def test_upvote_ratio_impact(self):
        scorer = RedditSentimentScorer()
        # High upvote ratio contributes positive score
        high_ratio = _make_post(title="Interesting", upvote_ratio=0.95)
        result_high = scorer.analyze_post(high_ratio)

        # Low upvote ratio contributes negative score
        low_ratio = _make_post(title="Interesting", upvote_ratio=0.1)
        result_low = scorer.analyze_post(low_ratio)

        assert result_high.score > result_low.score

    def test_comment_bonus(self):
        scorer = RedditSentimentScorer()
        comments = [
            RedditComment(user="u1", body="Great DD!", score=100),
            RedditComment(user="u2", body="Agree", score=50),
            RedditComment(user="u3", body="Bad take", score=-10),
        ]
        post = _make_post(title="Analysis", upvote_ratio=0.5, comments=comments)
        result = scorer.analyze_post(post)
        # 2 positive (>5) - 1 negative (<-2) = 1 * 0.5 = 0.5 bonus
        assert result.score != 0.0

    def test_score_rounding(self):
        scorer = RedditSentimentScorer()
        post = _make_post(title="test", upvote_ratio=0.73)
        result = scorer.analyze_post(post)
        # Score should be rounded to 2 decimal places
        assert result.score == round(result.score, 2)

    def test_custom_thresholds(self):
        scorer = RedditSentimentScorer(bullish_threshold=0.1, bearish_threshold=-0.1)
        post = _make_post(title="test", upvote_ratio=0.52)
        result = scorer.analyze_post(post)
        # (0.52 - 0.5) * 10 = 0.2 → bullish with low threshold
        assert result.label == "bullish"

    def test_analyze_posts_batch(self):
        scorer = RedditSentimentScorer()
        posts = [_make_post(title=f"Post {i}") for i in range(5)]
        results = scorer.analyze_posts(posts)
        assert len(results) == 5
        assert all(isinstance(r, RedditSentimentResult) for r in results)

    def test_comments_keywords_included(self):
        scorer = RedditSentimentScorer()
        comments = [
            RedditComment(user="u1", body="to the moon! bullish! buy!", score=1),
        ]
        post = _make_post(title="Thoughts?", upvote_ratio=0.5, comments=comments)
        result = scorer.analyze_post(post)
        assert result.bullish_hits >= 2

    def test_case_insensitive_keywords(self):
        scorer = RedditSentimentScorer()
        post = _make_post(title="BULLISH on this stock, CALLS printing")
        result = scorer.analyze_post(post)
        assert result.bullish_hits >= 2
