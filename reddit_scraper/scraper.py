"""Reddit 爬蟲 — 支援 PRAW (推薦) 與 public JSON API (fallback) 雙後端。

後端選擇邏輯:
1. 如果 praw 已安裝且環境變數 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET 有設定
   → 使用 PRAW (OAuth2, 600 req/min, 自動 rate limit backoff)
2. 否則 → fallback 到 public JSON API (60 req/min, 無認證)

⚠️ 生產環境強烈建議使用 PRAW。Public JSON API 在高頻率排程下
容易觸發 429 或 Shadowban。
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
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
    score: int = 0  # upvotes - downvotes
    upvote_ratio: float = 0.0
    num_comments: int = 0
    created_utc: float = 0.0
    flair: str = ""
    comments: list[RedditComment] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
# 抽象後端
# ──────────────────────────────────────────────────────────────


class _Backend(ABC):
    """Reddit 爬蟲後端介面。"""

    @abstractmethod
    def fetch_subreddit(
        self,
        subreddit: str,
        limit: int,
    ) -> list[RedditPost]: ...

    @abstractmethod
    def fetch_comments(self, post: RedditPost) -> list[RedditComment]: ...


# ──────────────────────────────────────────────────────────────
# PRAW 後端 (推薦)
# ──────────────────────────────────────────────────────────────


class _PrawBackend(_Backend):
    """使用 PRAW (Python Reddit API Wrapper) 的 OAuth2 後端。

    自動處理:
    - OAuth2 token 輪替
    - Rate limit backoff (429 自動等待)
    - 600 req/min 的更高限額
    """

    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        import praw  # noqa: F811 — lazy import

        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

    def fetch_subreddit(
        self,
        subreddit: str,
        limit: int,
    ) -> list[RedditPost]:
        posts: list[RedditPost] = []
        try:
            sub = self.reddit.subreddit(subreddit)
            for submission in sub.hot(limit=limit):
                if submission.stickied:
                    continue
                posts.append(
                    RedditPost(
                        title=submission.title,
                        url=f"{REDDIT_BASE_URL}{submission.permalink}",
                        subreddit=subreddit,
                        author=str(submission.author) if submission.author else "[deleted]",
                        selftext=submission.selftext or "",
                        score=submission.score,
                        upvote_ratio=submission.upvote_ratio,
                        num_comments=submission.num_comments,
                        created_utc=submission.created_utc,
                        flair=submission.link_flair_text or "",
                    )
                )
        except Exception as exc:
            print(f"[WARN] PRAW 無法取得 r/{subreddit}: {exc}")
        return posts

    def fetch_comments(self, post: RedditPost) -> list[RedditComment]:
        comments: list[RedditComment] = []
        try:
            submission = self.reddit.submission(url=post.url)
            submission.comments.replace_more(limit=0)  # 只取已載入的留言
            for comment in submission.comments[:50]:
                body = comment.body
                if body in ("[deleted]", "[removed]"):
                    continue
                comments.append(
                    RedditComment(
                        user=str(comment.author) if comment.author else "[deleted]",
                        body=body,
                        score=comment.score,
                    )
                )
        except Exception:
            pass
        return comments


# ──────────────────────────────────────────────────────────────
# Public JSON API 後端 (fallback)
# ──────────────────────────────────────────────────────────────


class _JsonBackend(_Backend):
    """使用 Reddit public JSON API 的無認證後端。

    ⚠️ 限制:
    - 約 60 req/min
    - 高頻率下容易被 429 / Shadowban
    - 不適合生產環境排程
    """

    def __init__(self, delay: float):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_subreddit(
        self,
        subreddit: str,
        limit: int,
    ) -> list[RedditPost]:
        url = f"{REDDIT_BASE_URL}/r/{subreddit}/hot.json"
        params = {"limit": limit, "raw_json": 1}

        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 10))
                print(f"[WARN] r/{subreddit} 被 rate limit，等待 {wait}s...")
                time.sleep(wait)
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
                continue

            permalink = post_data.get("permalink", "")
            posts.append(
                RedditPost(
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
                )
            )

        return posts

    def fetch_comments(self, post: RedditPost) -> list[RedditComment]:
        url = post.url.rstrip("/") + ".json"
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
            if body in ("[deleted]", "[removed]"):
                continue
            comments.append(
                RedditComment(
                    user=cdata.get("author", "[deleted]"),
                    body=body,
                    score=cdata.get("score", 0),
                )
            )

        return comments


# ──────────────────────────────────────────────────────────────
# 後端自動選擇
# ──────────────────────────────────────────────────────────────


def _auto_select_backend(delay: float) -> _Backend:
    """嘗試用 PRAW，失敗則 fallback 到 JSON API。"""
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")

    if client_id and client_secret:
        try:
            import praw  # noqa: F401

            user_agent = HEADERS["User-Agent"]
            backend = _PrawBackend(client_id, client_secret, user_agent)
            print("[INFO] 使用 PRAW 後端 (OAuth2, 600 req/min)")
            return backend
        except ImportError:
            print("[WARN] REDDIT_CLIENT_ID 已設定但 praw 未安裝，" "fallback 到 public JSON API。")
            print("       pip install praw")

    print("[INFO] 使用 public JSON API 後端 (60 req/min)")
    return _JsonBackend(delay)


# ──────────────────────────────────────────────────────────────
# 公開介面
# ──────────────────────────────────────────────────────────────


class RedditScraper:
    """爬取 Reddit subreddit 的文章與留言。

    自動選擇後端:
    - 設定 REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET + pip install praw → PRAW
    - 否則 → public JSON API (fallback)

    Parameters
    ----------
    subreddits : list[str]
        要爬的 subreddit 列表。
    delay : float
        每次 HTTP 請求間的延遲秒數 (僅 JSON 後端使用)。
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
        self._backend = _auto_select_backend(delay)

    def fetch_posts(self, limit: int = 25) -> list[RedditPost]:
        """從所有指定 subreddit 抓取最新文章。

        Parameters
        ----------
        limit : int
            每個 subreddit 抓幾篇（Reddit API 上限 100）。
        """
        all_posts: list[RedditPost] = []

        for sub in self.subreddits:
            posts = self._backend.fetch_subreddit(sub, limit=min(limit, 100))
            if self.fetch_comments:
                for post in posts:
                    comments = self._backend.fetch_comments(post)
                    post.comments = comments
                    if isinstance(self._backend, _JsonBackend):
                        time.sleep(self.delay)
            all_posts.extend(posts)

        return all_posts
