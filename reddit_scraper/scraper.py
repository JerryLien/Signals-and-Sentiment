"""Reddit 爬蟲 — 透過 public JSON API 抓取 subreddit 文章與留言。

Reddit 的 public JSON API 不需要認證，只要在 URL 後加 .json 即可。
Rate limit 約 60 req/min，我們用 1 秒間隔保持禮貌。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

from reddit_scraper.config import (
    DEFAULT_SUBREDDITS,
    HEADERS,
    REDDIT_BASE_URL,
    REQUEST_DELAY,
)


@dataclass
class RedditComment:
    """單一 Reddit 留言。"""

    user: str
    body: str
    score: int  # upvotes - downvotes


@dataclass
class RedditPost:
    """一篇 Reddit 文章。"""

    title: str
    url: str
    subreddit: str
    author: str = ""
    selftext: str = ""
    score: int = 0           # upvotes - downvotes
    upvote_ratio: float = 0.0
    num_comments: int = 0
    created_utc: float = 0.0
    flair: str = ""
    comments: list[RedditComment] = field(default_factory=list)


class RedditScraper:
    """爬取 Reddit subreddit 的文章與留言（使用 public JSON API）。

    Parameters
    ----------
    subreddits : list[str]
        要爬的 subreddit 列表。
    delay : float
        每次 HTTP 請求間的延遲秒數。
    fetch_comments : bool
        是否進入文章內頁抓留言（較慢，但情緒分析更準確）。
    """

    def __init__(
        self,
        subreddits: list[str] | None = None,
        delay: float = REQUEST_DELAY,
        fetch_comments: bool = False,
    ):
        self.subreddits = subreddits or DEFAULT_SUBREDDITS
        self.delay = delay
        self.fetch_comments = fetch_comments
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_posts(self, limit: int = 25) -> list[RedditPost]:
        """從所有指定 subreddit 抓取最新文章。

        Parameters
        ----------
        limit : int
            每個 subreddit 抓幾篇（Reddit API 上限 100）。
        """
        all_posts: list[RedditPost] = []

        for sub in self.subreddits:
            posts = self._fetch_subreddit(sub, limit=min(limit, 100))
            if self.fetch_comments:
                for post in posts:
                    comments = self._fetch_post_comments(post.url)
                    post.comments = comments
                    time.sleep(self.delay)
            all_posts.extend(posts)

        return all_posts

    def _fetch_subreddit(self, subreddit: str, limit: int) -> list[RedditPost]:
        """取得單一 subreddit 的文章列表。"""
        url = f"{REDDIT_BASE_URL}/r/{subreddit}/hot.json"
        params = {"limit": limit, "raw_json": 1}

        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[WARN] 無法取得 r/{subreddit}: {exc}")
            return []

        time.sleep(self.delay)

        posts: list[RedditPost] = []
        data = resp.json().get("data", {})

        for child in data.get("children", []):
            post_data = child.get("data", {})
            if post_data.get("stickied"):
                continue  # 跳過置頂文

            permalink = post_data.get("permalink", "")
            posts.append(RedditPost(
                title=post_data.get("title", ""),
                url=f"{REDDIT_BASE_URL}{permalink}",
                subreddit=subreddit,
                author=post_data.get("author", "[deleted]"),
                selftext=post_data.get("selftext", ""),
                score=post_data.get("score", 0),
                upvote_ratio=post_data.get("upvote_ratio", 0.0),
                num_comments=post_data.get("num_comments", 0),
                created_utc=post_data.get("created_utc", 0.0),
                flair=post_data.get("link_flair_text", "") or "",
            ))

        return posts

    def _fetch_post_comments(self, post_url: str) -> list[RedditComment]:
        """取得單篇文章的留言（只取第一層）。"""
        url = post_url.rstrip("/") + ".json"
        params = {"limit": 50, "raw_json": 1}

        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException:
            return []

        comments: list[RedditComment] = []
        listings = resp.json()

        if len(listings) < 2:
            return comments

        for child in listings[1].get("data", {}).get("children", []):
            if child.get("kind") != "t1":
                continue
            cdata = child.get("data", {})
            body = cdata.get("body", "")
            if body == "[deleted]" or body == "[removed]":
                continue
            comments.append(RedditComment(
                user=cdata.get("author", "[deleted]"),
                body=body,
                score=cdata.get("score", 0),
            ))

        return comments
