"""Tests for ptt_scraper.scraper — HTTP 行為測試 (mock)."""

from unittest.mock import MagicMock, patch

from ptt_scraper.scraper import PttScraper

# 模擬 PTT 列表頁 HTML
_INDEX_HTML = """
<html><body>
<div class="r-ent">
  <div class="title"><a href="/bbs/Stock/M.111.A.222.html">測試文章一</a></div>
</div>
<div class="r-ent">
  <div class="title"><a href="/bbs/Stock/M.333.A.444.html">測試文章二</a></div>
</div>
<div class="btn-group btn-group-paging">
  <a href="/bbs/Stock/index999.html">‹ 上頁</a>
</div>
</body></html>
"""

# 模擬 PTT 文章內頁 HTML
_POST_HTML = """
<html><body>
<div id="main-content">
  <div class="article-metaline">
    <span class="article-meta-tag">作者</span>
    <span class="article-meta-value">testuser (測試)</span>
  </div>
  <div class="article-metaline">
    <span class="article-meta-tag">時間</span>
    <span class="article-meta-value">Mon Jan  1 12:00:00 2026</span>
  </div>
  這是內文。台積電今天漲停了！

  <div class="push">
    <span class="push-tag">推 </span>
    <span class="push-userid">user1</span>
    <span class="push-content">: 讚</span>
  </div>
  <div class="push">
    <span class="push-tag">噓 </span>
    <span class="push-userid">user2</span>
    <span class="push-content">: 不看好</span>
  </div>
  <div class="push">
    <span class="push-tag">→ </span>
    <span class="push-userid">user3</span>
    <span class="push-content">: 觀望</span>
  </div>
</div>
</body></html>
"""


class TestPttScraperParsing:
    """測試 PttScraper 的 HTML 解析邏輯（使用 mock HTTP）。"""

    def test_get_post_list(self):
        scraper = PttScraper(board="Stock", delay=0)
        mock_resp = MagicMock()
        mock_resp.text = _INDEX_HTML
        mock_resp.raise_for_status = MagicMock()
        scraper.session.get = MagicMock(return_value=mock_resp)

        posts, prev_url = scraper._get_post_list("https://www.ptt.cc/bbs/Stock/index.html")
        assert len(posts) == 2
        assert posts[0].title == "測試文章一"
        assert posts[1].title == "測試文章二"
        assert prev_url is not None
        assert "index999" in prev_url

    def test_get_post_list_no_prev(self):
        scraper = PttScraper(board="Stock", delay=0)
        html = (
            '<html><body><div class="r-ent"><div class="title">'
            '<a href="/bbs/Stock/M.1.A.2.html">標題</a></div></div></body></html>'
        )
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        scraper.session.get = MagicMock(return_value=mock_resp)

        posts, prev_url = scraper._get_post_list("https://www.ptt.cc/bbs/Stock/index.html")
        assert len(posts) == 1
        assert prev_url is None

    def test_parse_post_extracts_content(self):
        scraper = PttScraper(board="Stock", delay=0)
        mock_resp = MagicMock()
        mock_resp.text = _POST_HTML
        mock_resp.raise_for_status = MagicMock()
        scraper.session.get = MagicMock(return_value=mock_resp)

        detail = scraper._parse_post("https://www.ptt.cc/bbs/Stock/M.111.A.222.html")
        assert detail is not None
        assert detail.author == "testuser (測試)"
        assert "台積電" in detail.content
        assert len(detail.comments) == 3

    def test_parse_post_comments_tags(self):
        scraper = PttScraper(board="Stock", delay=0)
        mock_resp = MagicMock()
        mock_resp.text = _POST_HTML
        mock_resp.raise_for_status = MagicMock()
        scraper.session.get = MagicMock(return_value=mock_resp)

        detail = scraper._parse_post("https://www.ptt.cc/bbs/Stock/M.111.A.222.html")
        tags = [c.tag for c in detail.comments]
        assert "推" in tags
        assert "噓" in tags
        assert "→" in tags

    def test_parse_post_http_error_returns_none(self):
        scraper = PttScraper(board="Stock", delay=0)
        import requests

        scraper.session.get = MagicMock(side_effect=requests.RequestException("timeout"))

        detail = scraper._parse_post("https://www.ptt.cc/bbs/Stock/M.111.A.222.html")
        assert detail is None

    @patch("ptt_scraper.scraper.time.sleep")
    def test_fetch_posts_integrates_detail(self, mock_sleep):
        scraper = PttScraper(board="Stock", delay=0)

        # First call: index page, second call: post detail
        mock_index = MagicMock()
        paging_html = (
            '<div class="btn-group btn-group-paging">\n'
            '  <a href="/bbs/Stock/index999.html">‹ 上頁</a>\n</div>'
        )
        mock_index.text = _INDEX_HTML.replace(paging_html, "")
        mock_index.raise_for_status = MagicMock()

        mock_detail = MagicMock()
        mock_detail.text = _POST_HTML
        mock_detail.raise_for_status = MagicMock()

        scraper.session.get = MagicMock(side_effect=[mock_index, mock_detail, mock_detail])

        posts = scraper.fetch_posts(max_pages=1)
        assert len(posts) == 2
        # Details should be populated
        assert posts[0].author == "testuser (測試)"
        assert len(posts[0].comments) == 3

    def test_extract_body_removes_signature(self):
        html = """
        <html><body>
        <div id="main-content">
        正文在這裡。

--
這是簽名檔，應該被移除。
        </div>
        </body></html>
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        main = soup.find("div", id="main-content")
        body = PttScraper._extract_body(main)
        assert "正文在這裡" in body
        assert "簽名檔" not in body

    def test_extract_body_removes_ansi(self):
        html = """
        <html><body>
        <div id="main-content">
        \x1b[32m綠色文字\x1b[0m
        </div>
        </body></html>
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        main = soup.find("div", id="main-content")
        body = PttScraper._extract_body(main)
        assert "\x1b" not in body
        assert "綠色文字" in body
