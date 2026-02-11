"""Tests for main.py — CLI 參數與輸出格式。"""

import io
from contextlib import redirect_stdout

from main import (
    _print_buzz,
    _print_contrarian,
    _print_output,
    _print_sectors,
    _print_sentiment_table,
)


class TestPrintSentimentTable:
    def test_ptt_format(self):
        results = [
            {
                "title": "台積電漲停",
                "sentiment": {"score": 5.0, "label": "bullish", "push": 10, "boo": 1, "arrow": 3},
                "entities": [{"ticker": "2330", "name": "台積電"}],
            },
            {
                "title": "今天跌了",
                "sentiment": {"score": -3.0, "label": "bearish", "push": 0, "boo": 5, "arrow": 1},
                "entities": [],
            },
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_sentiment_table(results)
        output = buf.getvalue()
        assert "情緒分析" in output
        assert "Bullish: 1" in output
        assert "Bearish: 1" in output
        assert "Total: 2" in output
        assert "2330" in output

    def test_reddit_format(self):
        results = [
            {
                "title": "NVDA to the moon",
                "subreddit": "wallstreetbets",
                "sentiment": {
                    "score": 4.5,
                    "label": "bullish",
                    "upvote_ratio": 0.92,
                    "post_score": 1500,
                    "bullish_hits": 3,
                    "bearish_hits": 0,
                },
                "entities": [{"ticker": "NVDA", "name": "NVIDIA"}],
            },
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_sentiment_table(results)
        output = buf.getvalue()
        assert "Upvt%" in output
        assert "NVDA" in output

    def test_empty_results(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_sentiment_table([])
        output = buf.getvalue()
        assert "Total: 0" in output


class TestPrintContrarian:
    def test_output_format(self):
        data = {
            "total_posts": 100,
            "capitulation_count": 10,
            "euphoria_count": 5,
            "capitulation_ratio": 0.10,
            "euphoria_ratio": 0.05,
            "market_signal": "fear",
            "capitulation_posts": [
                {"title": "畢業了", "hits": ["畢業", "賠光"]},
            ],
            "euphoria_posts": [],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_contrarian(data)
        output = buf.getvalue()
        assert "反指標偵測" in output
        assert "偏恐慌" in output
        assert "畢業了" in output
        assert "10/100" in output

    def test_extreme_fear(self):
        data = {
            "total_posts": 50,
            "capitulation_count": 15,
            "euphoria_count": 0,
            "capitulation_ratio": 0.30,
            "euphoria_ratio": 0.0,
            "market_signal": "extreme_fear",
            "capitulation_posts": [],
            "euphoria_posts": [],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_contrarian(data)
        assert "極度恐慌" in buf.getvalue()


class TestPrintBuzz:
    def test_output_with_anomalies(self):
        data = {
            "total_posts": 50,
            "tickers": [
                {
                    "ticker": "2330",
                    "name": "台積電",
                    "mentions": 20,
                    "buzz_score": 3.5,
                    "anomaly": True,
                },
                {
                    "ticker": "2317",
                    "name": "鴻海",
                    "mentions": 5,
                    "buzz_score": 0.5,
                    "anomaly": False,
                },
            ],
            "anomalies": [
                {"ticker": "2330", "name": "台積電", "buzz_score": 3.5},
            ],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_buzz(data)
        output = buf.getvalue()
        assert "異常熱度偵測" in output
        assert "2330" in output
        assert "異常標的" in output

    def test_no_anomalies(self):
        data = {
            "total_posts": 10,
            "tickers": [
                {
                    "ticker": "2330",
                    "name": "台積電",
                    "mentions": 3,
                    "buzz_score": 0.5,
                    "anomaly": False,
                },
            ],
            "anomalies": [],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_buzz(data)
        output = buf.getvalue()
        assert "異常標的" not in output


class TestPrintSectors:
    def test_output_format(self):
        data = {
            "ranking": [
                {
                    "sector": "AI伺服器",
                    "mentions": 30,
                    "keywords": ["ai伺服器", "gpu"],
                    "sample_titles": ["標題1"],
                },
                {"sector": "半導體", "mentions": 15, "keywords": ["半導體"], "sample_titles": []},
            ],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_sectors(data)
        output = buf.getvalue()
        assert "板塊輪動" in output
        assert "AI伺服器" in output
        assert "半導體" in output
        assert "█" in output

    def test_empty_ranking(self):
        data = {"ranking": []}
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_sectors(data)
        assert "未偵測到" in buf.getvalue()


class TestPrintOutput:
    def test_dispatches_all_sections(self):
        output = {
            "sentiment": [
                {
                    "title": "test",
                    "sentiment": {
                        "score": 0.0,
                        "label": "neutral",
                        "push": 0,
                        "boo": 0,
                        "arrow": 0,
                    },
                    "entities": [],
                },
            ],
            "contrarian": {
                "total_posts": 1,
                "capitulation_count": 0,
                "euphoria_count": 0,
                "capitulation_ratio": 0.0,
                "euphoria_ratio": 0.0,
                "market_signal": "neutral",
                "capitulation_posts": [],
                "euphoria_posts": [],
            },
            "buzz": {
                "total_posts": 1,
                "tickers": [],
                "anomalies": [],
            },
            "sectors": {
                "ranking": [],
            },
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_output(output)
        text = buf.getvalue()
        assert "情緒分析" in text
        assert "反指標偵測" in text
        assert "異常熱度偵測" in text
        assert "板塊輪動" in text

    def test_empty_output(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _print_output({})
        assert buf.getvalue() == ""
