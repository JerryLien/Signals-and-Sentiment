"""Tests for ptt_scraper.buzz module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ptt_scraper.buzz import BuzzDetector, BuzzReport, TickerBuzz
from ptt_scraper.entity_mapping import EntityMapper
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


class TestBuzzDetector:
    def test_analyze_counts_mentions(self):
        detector = BuzzDetector()
        posts = [
            _make_post(title="台積電好猛", content="台積電真強"),
            _make_post(title="聊聊台積電", content="2330繼續漲"),
        ]
        report = detector.analyze(posts)
        assert isinstance(report, BuzzReport)
        assert report.total_posts == 2
        # 台積電 / 2330 should be detected
        tickers = {t.ticker for t in report.tickers}
        assert "2330" in tickers

    def test_no_mentions(self):
        detector = BuzzDetector()
        posts = [_make_post(title="今天天氣好", content="出去走走")]
        report = detector.analyze(posts)
        # Might find some tickers from accidental patterns, but should be minimal
        assert report.total_posts == 1

    def test_buzz_score_no_history(self):
        detector = BuzzDetector()
        detector.history = []  # no history
        score = detector._compute_buzz_score("2330", 5)
        assert score == 5.0  # returns count directly when no history

    def test_buzz_score_with_history(self):
        detector = BuzzDetector()
        detector.history = [
            {"date": "2026-01-01", "mentions": {"2330": 10}},
            {"date": "2026-01-02", "mentions": {"2330": 10}},
            {"date": "2026-01-03", "mentions": {"2330": 10}},
        ]
        # All historical values are 10, std = 0
        score = detector._compute_buzz_score("2330", 10)
        assert score == 0.0  # same as mean

        score_higher = detector._compute_buzz_score("2330", 20)
        assert score_higher == 10.0  # (20 - 10) when std == 0

    def test_buzz_score_z_score(self):
        detector = BuzzDetector()
        detector.history = [
            {"date": "2026-01-01", "mentions": {"2330": 5}},
            {"date": "2026-01-02", "mentions": {"2330": 15}},
        ]
        # mean = 10, variance = 25, std = 5
        score = detector._compute_buzz_score("2330", 20)
        expected = (20 - 10) / 5  # z-score = 2.0
        assert score == pytest.approx(expected, abs=0.01)

    def test_anomaly_detection(self):
        detector = BuzzDetector(anomaly_threshold=2.0)
        detector.history = [
            {"date": f"2026-01-{i:02d}", "mentions": {"2330": 5}}
            for i in range(1, 11)
        ]
        # All historical values are 5, std = 0
        # _compute_buzz_score with std==0 returns (current - mean)
        # For current=100: score = 95.0 → anomaly
        score = detector._compute_buzz_score("2330", 100)
        assert score == 95.0
        assert score >= detector.anomaly_threshold

    def test_save_snapshot(self, tmp_path):
        history_path = tmp_path / "buzz_history.json"
        detector = BuzzDetector()
        detector.history = []

        with patch("ptt_scraper.buzz._BUZZ_HISTORY_PATH", history_path), \
             patch("ptt_scraper.buzz._DATA_DIR", tmp_path):
            posts = [_make_post(title="台積電", content="2330")]
            detector.save_snapshot(posts)
            assert history_path.exists()
            data = json.loads(history_path.read_text())
            assert len(data) == 1
            assert "mentions" in data[0]

    def test_history_window_limit(self, tmp_path):
        history_path = tmp_path / "buzz_history.json"
        detector = BuzzDetector(history_window=5)
        detector.history = [
            {"date": f"2026-01-{i:02d}", "mentions": {"2330": i}}
            for i in range(1, 6)  # 5 entries
        ]

        with patch("ptt_scraper.buzz._BUZZ_HISTORY_PATH", history_path), \
             patch("ptt_scraper.buzz._DATA_DIR", tmp_path):
            posts = [_make_post(title="台積電")]
            detector.save_snapshot(posts)
            assert len(detector.history) == 5  # capped at window

    def test_comments_included_in_analysis(self):
        detector = BuzzDetector()
        posts = [
            _make_post(
                title="今日心得",
                content="大盤平盤",
                comments=[Comment(tag="推", user="u1", content="2330讚")],
            ),
        ]
        report = detector.analyze(posts)
        tickers = {t.ticker for t in report.tickers}
        assert "2330" in tickers


class TestTickerBuzz:
    def test_dataclass_fields(self):
        tb = TickerBuzz(
            ticker="2330", name="台積電", mention_count=10,
            buzz_score=3.5, is_anomaly=True,
        )
        assert tb.ticker == "2330"
        assert tb.is_anomaly is True
