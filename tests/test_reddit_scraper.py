"""Tests for reddit_scraper.scraper — HTTP 行為測試 (mock)."""

from unittest.mock import MagicMock, patch

from reddit_scraper.scraper import (
    RedditPost,
    RedditScraper,
    _JsonBackend,
)

# 模擬 Reddit JSON API 回應
_SUBREDDIT_JSON = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "NVDA to the moon",
                    "permalink": "/r/wallstreetbets/comments/abc123/nvda/",
                    "author": "yolo_trader",
                    "selftext": "Bought 100 calls",
                    "score": 1500,
                    "upvote_ratio": 0.92,
                    "num_comments": 300,
                    "created_utc": 1700000000.0,
                    "link_flair_text": "YOLO",
                    "stickied": False,
                }
            },
            {
                "data": {
                    "title": "Daily Discussion",
                    "permalink": "/r/wallstreetbets/comments/def456/daily/",
                    "author": "AutoModerator",
                    "selftext": "",
                    "score": 50,
                    "upvote_ratio": 0.8,
                    "num_comments": 5000,
                    "created_utc": 1700000000.0,
                    "link_flair_text": None,
                    "stickied": True,  # should be skipped
                }
            },
            {
                "data": {
                    "title": "Market crash incoming",
                    "permalink": "/r/wallstreetbets/comments/ghi789/crash/",
                    "author": "bear_king",
                    "selftext": "Sell everything, puts printing",
                    "score": 500,
                    "upvote_ratio": 0.65,
                    "num_comments": 120,
                    "created_utc": 1700000000.0,
                    "link_flair_text": "Discussion",
                    "stickied": False,
                }
            },
        ]
    }
}

_COMMENTS_JSON = [
    {"data": {}},  # listing[0] = post data
    {
        "data": {
            "children": [
                {
                    "kind": "t1",
                    "data": {
                        "author": "commenter1",
                        "body": "Great DD!",
                        "score": 50,
                    },
                },
                {
                    "kind": "t1",
                    "data": {
                        "author": "commenter2",
                        "body": "[deleted]",
                        "score": 1,
                    },
                },
                {
                    "kind": "t1",
                    "data": {
                        "author": "commenter3",
                        "body": "This is the way",
                        "score": 10,
                    },
                },
                {
                    "kind": "more",
                    "data": {},
                },
            ]
        }
    },
]


class TestJsonBackend:
    def test_fetch_subreddit_parses_posts(self):
        backend = _JsonBackend(delay=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _SUBREDDIT_JSON
        mock_resp.raise_for_status = MagicMock()
        backend.session.get = MagicMock(return_value=mock_resp)

        with patch("reddit_scraper.scraper.time.sleep"):
            posts = backend.fetch_subreddit("wallstreetbets", limit=25)

        # Stickied post should be filtered out
        assert len(posts) == 2
        assert posts[0].title == "NVDA to the moon"
        assert posts[0].author == "yolo_trader"
        assert posts[0].score == 1500
        assert posts[0].upvote_ratio == 0.92
        assert posts[0].subreddit == "wallstreetbets"
        assert posts[1].title == "Market crash incoming"

    def test_fetch_subreddit_handles_error(self):
        backend = _JsonBackend(delay=0)
        import requests

        backend.session.get = MagicMock(side_effect=requests.RequestException("timeout"))

        with patch("reddit_scraper.scraper.time.sleep"):
            posts = backend.fetch_subreddit("wallstreetbets", limit=25)
        assert posts == []

    def test_fetch_comments_parses_response(self):
        backend = _JsonBackend(delay=0)
        mock_resp = MagicMock()
        mock_resp.json.return_value = _COMMENTS_JSON
        mock_resp.raise_for_status = MagicMock()
        backend.session.get = MagicMock(return_value=mock_resp)

        post = RedditPost(
            title="test",
            url="https://www.reddit.com/r/wsb/comments/abc/test/",
            subreddit="wsb",
        )
        comments = backend.fetch_comments(post)
        # [deleted] should be filtered, "more" kind should be filtered
        assert len(comments) == 2
        assert comments[0].body == "Great DD!"
        assert comments[1].body == "This is the way"

    def test_fetch_comments_handles_error(self):
        backend = _JsonBackend(delay=0)
        import requests

        backend.session.get = MagicMock(side_effect=requests.RequestException("err"))
        post = RedditPost(title="t", url="https://www.reddit.com/r/wsb/test/", subreddit="wsb")
        comments = backend.fetch_comments(post)
        assert comments == []

    def test_fetch_subreddit_rate_limit_retry(self):
        backend = _JsonBackend(delay=0)

        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "1"}

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = _SUBREDDIT_JSON
        mock_ok.raise_for_status = MagicMock()

        backend.session.get = MagicMock(side_effect=[mock_429, mock_ok])

        with patch("reddit_scraper.scraper.time.sleep"):
            posts = backend.fetch_subreddit("wallstreetbets", limit=25)
        assert len(posts) == 2


class TestRedditScraper:
    @patch("reddit_scraper.scraper._auto_select_backend")
    def test_fetch_posts_from_multiple_subs(self, mock_backend_factory):
        mock_backend = MagicMock()
        mock_backend.fetch_subreddit.return_value = [
            RedditPost(title="Post1", url="http://test/1", subreddit="wsb"),
        ]
        mock_backend_factory.return_value = mock_backend

        scraper = RedditScraper(subreddits=["wsb", "stocks"], delay=0)
        posts = scraper.fetch_posts(limit=10)
        assert len(posts) == 2  # 1 per sub * 2 subs
        assert mock_backend.fetch_subreddit.call_count == 2

    @patch("reddit_scraper.scraper._auto_select_backend")
    def test_fetch_posts_limit_capped_at_100(self, mock_backend_factory):
        mock_backend = MagicMock()
        mock_backend.fetch_subreddit.return_value = []
        mock_backend_factory.return_value = mock_backend

        scraper = RedditScraper(subreddits=["wsb"], delay=0)
        scraper.fetch_posts(limit=200)
        mock_backend.fetch_subreddit.assert_called_with("wsb", limit=100)

    @patch("reddit_scraper.scraper._auto_select_backend")
    def test_fetch_comments_when_enabled(self, mock_backend_factory):
        mock_backend = MagicMock()
        post = RedditPost(title="Post1", url="http://test/1", subreddit="wsb")
        mock_backend.fetch_subreddit.return_value = [post]
        mock_backend.fetch_comments.return_value = []
        mock_backend_factory.return_value = mock_backend

        scraper = RedditScraper(subreddits=["wsb"], delay=0, fetch_comments=True)
        scraper.fetch_posts(limit=10)
        mock_backend.fetch_comments.assert_called_once()

    @patch("reddit_scraper.scraper._auto_select_backend")
    def test_no_comments_by_default(self, mock_backend_factory):
        mock_backend = MagicMock()
        mock_backend.fetch_subreddit.return_value = [
            RedditPost(title="Post1", url="http://test/1", subreddit="wsb"),
        ]
        mock_backend_factory.return_value = mock_backend

        scraper = RedditScraper(subreddits=["wsb"], delay=0)
        scraper.fetch_posts(limit=10)
        mock_backend.fetch_comments.assert_not_called()

    @patch("reddit_scraper.scraper._auto_select_backend")
    def test_default_subreddits(self, mock_backend_factory):
        mock_backend = MagicMock()
        mock_backend.fetch_subreddit.return_value = []
        mock_backend_factory.return_value = mock_backend

        scraper = RedditScraper(delay=0)
        assert len(scraper.subreddits) == 7
        assert "wallstreetbets" in scraper.subreddits
