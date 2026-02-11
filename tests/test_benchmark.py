"""Benchmark tests — 驗證解析效能不退化。

用 pytest 內建計時，不依賴 pytest-benchmark。
每個 benchmark 跑 N 次迴圈，斷言平均耗時在合理範圍內。
"""

import time

from ptt_scraper.buzz import BuzzDetector
from ptt_scraper.contrarian import summarize_contrarian
from ptt_scraper.entity_mapping import EntityMapper
from ptt_scraper.scraper import Comment, Post
from ptt_scraper.sectors import SectorTracker
from ptt_scraper.sentiment import SentimentScorer
from reddit_scraper.entity_mapping import RedditEntityMapper
from reddit_scraper.sentiment import RedditSentimentScorer
from reddit_scraper.scraper import RedditComment, RedditPost


def _make_ptt_posts(n: int) -> list[Post]:
    return [
        Post(
            title=f"台積電法說會重點{i}",
            url=f"https://www.ptt.cc/bbs/Stock/M.{i}.A.001.html",
            author="testuser",
            date="1/01",
            content="護國神山台積電今天股價創新高，半導體產業鏈受惠，AI伺服器出貨量大增。"
            "鴻海也跟著漲，航運股今天比較弱勢。2330 繼續看好。",
            comments=[Comment(tag="推", user=f"user{j}", content="推 台積電讚") for j in range(10)]
            + [Comment(tag="噓", user=f"boo{j}", content="噓 太貴了") for j in range(3)]
            + [Comment(tag="→", user=f"arr{j}", content="觀望中") for j in range(5)],
        )
        for i in range(n)
    ]


def _make_reddit_posts(n: int) -> list[RedditPost]:
    return [
        RedditPost(
            title=f"NVDA earnings beat {i}! $TSLA to the moon",
            url=f"https://www.reddit.com/r/wallstreetbets/comments/abc{i}/test/",
            subreddit="wallstreetbets",
            author="yolo_trader",
            selftext="nvidia just crushed earnings, jensen leather jacket man is a genius. "
            "su bae AMD also looking good. Buying $AAPL $MSFT calls. "
            "bitcoin ethereum solana all pumping. Diamond hands!",
            score=1500,
            upvote_ratio=0.92,
            num_comments=300,
            comments=[
                RedditComment(user=f"u{j}", body="Great DD! Bullish!", score=50) for j in range(5)
            ],
        )
        for i in range(n)
    ]


class TestBenchmarkPttSentiment:
    def test_sentiment_100_posts(self):
        scorer = SentimentScorer()
        posts = _make_ptt_posts(100)

        start = time.perf_counter()
        for post in posts:
            scorer.analyze_post(post)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 5.0, f"PTT sentiment avg {avg_ms:.2f}ms/post (limit: 5ms)"


class TestBenchmarkPttEntityMapping:
    def test_entity_mapping_100_posts(self):
        mapper = EntityMapper()
        posts = _make_ptt_posts(100)

        start = time.perf_counter()
        for post in posts:
            mapper.find_entities(post.title + " " + post.content)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 10.0, f"PTT entity mapping avg {avg_ms:.2f}ms/post (limit: 10ms)"


class TestBenchmarkContrarian:
    def test_contrarian_100_posts(self):
        posts = _make_ptt_posts(100)

        start = time.perf_counter()
        summarize_contrarian(posts)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Contrarian analysis took {elapsed:.2f}s (limit: 1s)"


class TestBenchmarkBuzz:
    def test_buzz_100_posts(self):
        detector = BuzzDetector()
        posts = _make_ptt_posts(100)

        start = time.perf_counter()
        detector.analyze(posts)
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"Buzz analysis took {elapsed:.2f}s (limit: 2s)"


class TestBenchmarkSectors:
    def test_sectors_100_posts(self):
        tracker = SectorTracker()
        posts = _make_ptt_posts(100)

        start = time.perf_counter()
        tracker.analyze(posts)
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Sector analysis took {elapsed:.2f}s (limit: 1s)"


class TestBenchmarkRedditSentiment:
    def test_reddit_sentiment_100_posts(self):
        scorer = RedditSentimentScorer()
        posts = _make_reddit_posts(100)

        start = time.perf_counter()
        for post in posts:
            scorer.analyze_post(post)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 5.0, f"Reddit sentiment avg {avg_ms:.2f}ms/post (limit: 5ms)"


class TestBenchmarkRedditEntityMapping:
    def test_reddit_entity_mapping_100_posts(self):
        mapper = RedditEntityMapper()
        posts = _make_reddit_posts(100)

        start = time.perf_counter()
        for post in posts:
            mapper.find_entities(post.title + " " + post.selftext)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / 100) * 1000
        assert avg_ms < 10.0, f"Reddit entity mapping avg {avg_ms:.2f}ms/post (limit: 10ms)"
