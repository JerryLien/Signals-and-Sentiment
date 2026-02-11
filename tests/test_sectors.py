"""Tests for ptt_scraper.sectors module."""

from ptt_scraper.scraper import Comment, Post
from ptt_scraper.sectors import SectorHeat, SectorReport, SectorTracker


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


class TestSectorTracker:
    def test_detect_ai_sector(self):
        tracker = SectorTracker()
        posts = [
            _make_post(title="AI伺服器出貨暴增", content="GPU需求持續成長"),
            _make_post(title="輝達財報亮眼", content="算力需求大增"),
        ]
        report = tracker.analyze(posts)
        assert report.total_posts == 2
        sector_names = [s.sector for s in report.sectors]
        assert "AI伺服器" in sector_names

    def test_detect_semiconductor_sector(self):
        tracker = SectorTracker()
        posts = [
            _make_post(title="台積電先進封裝", content="CoWoS產能滿載"),
        ]
        report = tracker.analyze(posts)
        sector_names = [s.sector for s in report.sectors]
        assert "半導體" in sector_names

    def test_detect_shipping_sector(self):
        tracker = SectorTracker()
        posts = [
            _make_post(title="航運股起飛", content="運價飆漲貨櫃爆量"),
        ]
        report = tracker.analyze(posts)
        sector_names = [s.sector for s in report.sectors]
        assert "航運" in sector_names

    def test_no_sectors_found(self):
        tracker = SectorTracker()
        posts = [_make_post(title="今天吃什麼", content="午餐好難選")]
        report = tracker.analyze(posts)
        assert report.total_posts == 1
        # Most sectors should have 0 mentions and be filtered out
        assert all(s.mention_count > 0 for s in report.sectors)

    def test_ranking_order(self):
        tracker = SectorTracker()
        posts = [
            _make_post(title="半導體晶圓代工", content="半導體半導體半導體"),
            _make_post(title="航運一篇", content="運價漲"),
        ]
        report = tracker.analyze(posts)
        if len(report.sectors) >= 2:
            # First sector should have more mentions
            assert report.sectors[0].mention_count >= report.sectors[1].mention_count

    def test_top_sector_property(self):
        report = SectorReport(total_posts=1, sectors=[
            SectorHeat(sector="AI伺服器", mention_count=10),
            SectorHeat(sector="航運", mention_count=5),
        ])
        assert report.top_sector == "AI伺服器"

    def test_top_sector_empty(self):
        report = SectorReport(total_posts=0, sectors=[])
        assert report.top_sector == ""

    def test_sample_titles_max_three(self):
        tracker = SectorTracker()
        posts = [
            _make_post(title=f"半導體新聞{i}", content="晶圓代工") for i in range(5)
        ]
        report = tracker.analyze(posts)
        semi = next((s for s in report.sectors if s.sector == "半導體"), None)
        if semi:
            assert len(semi.sample_titles) <= 3

    def test_matched_keywords_dedup(self):
        tracker = SectorTracker()
        posts = [
            _make_post(title="半導體", content="半導體"),
            _make_post(title="半導體", content="半導體"),
        ]
        report = tracker.analyze(posts)
        semi = next((s for s in report.sectors if s.sector == "半導體"), None)
        if semi:
            lower_kws = [k.lower() for k in semi.matched_keywords]
            assert len(lower_kws) == len(set(lower_kws))

    def test_extra_sectors(self):
        tracker = SectorTracker(extra_sectors={
            "太空": {"keywords": ["火箭", "衛星", "spacex"], "tickers": []},
        })
        posts = [_make_post(title="火箭發射成功", content="衛星通訊概念股")]
        report = tracker.analyze(posts)
        sector_names = [s.sector for s in report.sectors]
        assert "太空" in sector_names

    def test_comments_included(self):
        tracker = SectorTracker()
        posts = [
            _make_post(
                title="今天盤勢",
                content="平盤整理",
                comments=[Comment(tag="推", user="u1", content="半導體最強")],
            ),
        ]
        report = tracker.analyze(posts)
        semi = next((s for s in report.sectors if s.sector == "半導體"), None)
        assert semi is not None
        assert semi.mention_count >= 1
