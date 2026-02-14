"""Tests for ptt_scraper.store — InfluxDB 寫入邏輯 (mock)."""

from unittest.mock import MagicMock, patch

from ptt_scraper.store import InfluxStore


def _make_ptt_sentiment():
    return [
        {
            "title": "台積電好強",
            "sentiment": {"score": 5.0, "label": "bullish", "push": 10, "boo": 1, "arrow": 3},
            "entities": [{"ticker": "2330", "name": "台積電"}],
        },
        {
            "title": "今天大跌",
            "sentiment": {"score": -3.0, "label": "bearish", "push": 1, "boo": 5, "arrow": 2},
            "entities": [],
        },
        {
            "title": "觀望中",
            "sentiment": {"score": 0.0, "label": "neutral", "push": 2, "boo": 2, "arrow": 5},
            "entities": [{"ticker": "2317", "name": "鴻海"}],
        },
    ]


def _make_reddit_sentiment():
    return [
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


def _make_contrarian():
    return {
        "total_posts": 50,
        "capitulation_count": 5,
        "euphoria_count": 2,
        "capitulation_ratio": 0.10,
        "euphoria_ratio": 0.04,
        "market_signal": "fear",
    }


def _make_buzz():
    return {
        "total_posts": 50,
        "tickers": [
            {
                "ticker": "2330",
                "name": "台積電",
                "mentions": 20,
                "buzz_score": 3.5,
                "anomaly": True,
            },
            {"ticker": "2317", "name": "鴻海", "mentions": 8, "buzz_score": 1.2, "anomaly": False},
        ],
    }


def _make_sectors():
    return {
        "total_posts": 50,
        "ranking": [
            {"sector": "AI伺服器", "mentions": 30, "keywords": ["ai伺服器", "gpu"]},
            {"sector": "半導體", "mentions": 20, "keywords": ["半導體", "晶圓"]},
        ],
    }


class TestInfluxStore:
    @patch("ptt_scraper.store.InfluxDBClient")
    def test_write_sentiment_ptt(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        store = InfluxStore()
        results = _make_ptt_sentiment()
        count = store.write_sentiment(results, "Stock", source="ptt")
        # 3 posts + 1 board summary = 4 points
        assert count == 4
        mock_write_api.write.assert_called_once()
        points = mock_write_api.write.call_args.kwargs.get(
            "record", mock_write_api.write.call_args[1].get("record")
        )
        assert len(points) == 4

    @patch("ptt_scraper.store.InfluxDBClient")
    def test_write_sentiment_reddit(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        store = InfluxStore()
        results = _make_reddit_sentiment()
        count = store.write_sentiment(results, "wallstreetbets", source="reddit")
        # 1 post + 1 board summary = 2 points
        assert count == 2

    @patch("ptt_scraper.store.InfluxDBClient")
    def test_write_contrarian(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        store = InfluxStore()
        count = store.write_contrarian(_make_contrarian(), "Stock")
        assert count == 1
        mock_write_api.write.assert_called_once()

    @patch("ptt_scraper.store.InfluxDBClient")
    def test_write_buzz(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        store = InfluxStore()
        count = store.write_buzz(_make_buzz(), "Stock")
        assert count == 2  # 2 tickers
        mock_write_api.write.assert_called_once()

    @patch("ptt_scraper.store.InfluxDBClient")
    def test_write_sectors(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        store = InfluxStore()
        count = store.write_sectors(_make_sectors(), "Stock")
        assert count == 2  # 2 sectors
        mock_write_api.write.assert_called_once()

    @patch("ptt_scraper.store.InfluxDBClient")
    def test_write_all_dispatches(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        store = InfluxStore()
        output = {
            "sentiment": _make_ptt_sentiment(),
            "contrarian": _make_contrarian(),
            "buzz": _make_buzz(),
            "sectors": _make_sectors(),
        }
        total = store.write_all(output, "Stock", source="ptt")
        # 4 (sentiment) + 1 (contrarian) + 2 (buzz) + 2 (sectors) = 9
        assert total == 9

    @patch("ptt_scraper.store.InfluxDBClient")
    def test_write_all_partial(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        store = InfluxStore()
        output = {"sentiment": _make_ptt_sentiment()}
        total = store.write_all(output, "Stock")
        assert total == 4  # only sentiment

    @patch("ptt_scraper.store.InfluxDBClient")
    def test_write_all_empty(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        store = InfluxStore()
        total = store.write_all({}, "Stock")
        assert total == 0

    @patch("ptt_scraper.store.InfluxDBClient")
    def test_close(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.write_api.return_value = MagicMock()

        store = InfluxStore()
        store.close()
        mock_client.close.assert_called_once()

    @patch("ptt_scraper.store.InfluxDBClient")
    def test_sentiment_empty_results(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_write_api = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        store = InfluxStore()
        count = store.write_sentiment([], "Stock")
        assert count == 1  # only board summary point
