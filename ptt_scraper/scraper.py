"""PTT 網頁版爬蟲 - 抓取看板文章列表、內文與推文。"""

import logging
import re
import time
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from ptt_scraper.config import (
    DEFAULT_BOARD,
    HEADERS,
    PTT_BASE_URL,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


@dataclass
class Comment:
    """單一推文。"""

    tag: str  # 推 / 噓 / →
    user: str
    content: str


@dataclass
class Post:
    """一篇 PTT 文章。"""

    title: str
    url: str
    author: str = ""
    date: str = ""
    content: str = ""
    comments: list[Comment] = field(default_factory=list)


class PttScraper:
    """爬取 PTT 網頁版 (www.ptt.cc) 的文章與推文。

    Parameters
    ----------
    board : str
        目標看板名稱，預設為 Stock。
    delay : float
        每次 HTTP 請求間的延遲秒數。
    """

    def __init__(self, board: str = DEFAULT_BOARD, delay: float = REQUEST_DELAY):
        self.board = board
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ------------------------------------------------------------------
    # 公開方法
    # ------------------------------------------------------------------

    def fetch_posts(self, max_pages: int = 1) -> list[Post]:
        """從最新一頁開始往前爬，回傳 Post 列表（含內文與推文）。"""
        url: str | None = f"{PTT_BASE_URL}/bbs/{self.board}/index.html"
        all_posts: list[Post] = []

        for _ in range(max_pages):
            if url is None:
                break
            posts, prev_url = self._get_post_list(url)
            for post in posts:
                detail = self._parse_post(post.url)
                if detail:
                    post.author = detail.author
                    post.date = detail.date
                    post.content = detail.content
                    post.comments = detail.comments
                all_posts.append(post)
                time.sleep(self.delay)
            url = prev_url

        return all_posts

    # ------------------------------------------------------------------
    # 內部方法
    # ------------------------------------------------------------------

    def _get_post_list(self, url: str) -> tuple[list[Post], str | None]:
        """解析列表頁，回傳 (文章列表, 上一頁 URL)。"""
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts: list[Post] = []
        for div in soup.find_all("div", class_="r-ent"):
            title_div = div.find("div", class_="title")
            if title_div and title_div.a:
                title = title_div.a.text.strip()
                link = PTT_BASE_URL + title_div.a["href"]
                posts.append(Post(title=title, url=link))

        prev_url = self._extract_prev_url(soup)
        return posts, prev_url

    def _parse_post(self, url: str) -> Post | None:
        """解析文章內頁，回傳含內文與推文的 Post（僅填入 detail 欄位）。"""
        try:
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("無法取得 %s: %s", url, exc)
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        main = soup.find("div", id="main-content")
        if main is None:
            return None

        meta = self._extract_meta(main)
        comments = self._extract_comments(main)
        content = self._extract_body(main)

        return Post(
            title="",
            url=url,
            author=meta.get("作者", ""),
            date=meta.get("時間", ""),
            content=content,
            comments=comments,
        )

    # ------------------------------------------------------------------
    # 解析輔助
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_meta(main) -> dict[str, str]:
        meta_info: dict[str, str] = {}
        for ml in main.find_all("div", class_="article-metaline"):
            tag_el = ml.find("span", class_="article-meta-tag")
            val_el = ml.find("span", class_="article-meta-value")
            if tag_el and val_el:
                meta_info[tag_el.text.strip()] = val_el.text.strip()
            ml.extract()
        # 也移除 metaline-right（IP / 編輯紀錄）
        for mr in main.find_all("div", class_="article-metaline-right"):
            mr.extract()
        return meta_info

    @staticmethod
    def _extract_comments(main) -> list[Comment]:
        comments: list[Comment] = []
        for push in main.find_all("div", class_="push"):
            tag_el = push.find("span", class_="push-tag")
            user_el = push.find("span", class_="push-userid")
            content_el = push.find("span", class_="push-content")
            if tag_el and user_el and content_el:
                comments.append(
                    Comment(
                        tag=tag_el.text.strip(),
                        user=user_el.text.strip(),
                        content=content_el.text.lstrip(": ").strip(),
                    )
                )
            push.extract()
        return comments

    @staticmethod
    def _extract_body(main) -> str:
        """移除殘留標記後取得純文字內文。"""
        # 移除 f2 class (通常是文末的 URL 資訊)
        for el in main.find_all("span", class_="f2"):
            el.extract()

        raw = main.text.strip()
        # 清除 ANSI 殘留與連續空行
        raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        # 移除常見簽名檔分隔線之後的內容
        raw = re.split(r"\n--\n", raw, maxsplit=1)[0].strip()
        return raw

    @staticmethod
    def _extract_prev_url(soup) -> str | None:
        paging = soup.find("div", class_="btn-group btn-group-paging")
        if paging is None:
            return None
        links = paging.find_all("a")
        for link in links:
            if "上頁" in link.text:
                return PTT_BASE_URL + str(link["href"])
        return None
