"""動態暱稱更新 (feed.py) 的測試 — mock TWSE/TPEX API。"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from ptt_scraper.feed import (
    _parse_price,
    _fetch_twse_quotes,
    _fetch_tpex_quotes,
    compute_dynamic_aliases,
    update_dynamic_aliases,
)

# ------------------------------------------------------------------
# _parse_price
# ------------------------------------------------------------------


class TestParsePrice:
    def test_normal(self):
        assert _parse_price("123.45") == 123.45

    def test_comma(self):
        assert _parse_price("1,234.5") == 1234.5

    def test_invalid(self):
        assert _parse_price("N/A") is None

    def test_empty(self):
        assert _parse_price("") is None

    def test_none(self):
        assert _parse_price(None) is None


# ------------------------------------------------------------------
# _fetch_twse_quotes
# ------------------------------------------------------------------

TWSE_SAMPLE = [
    {"Code": "2330", "Name": "台積電", "ClosingPrice": "1,050"},
    {"Code": "2317", "Name": "鴻海", "ClosingPrice": "180.5"},
    {"Code": "9999", "Name": "壞資料", "ClosingPrice": "N/A"},
]


class TestFetchTwseQuotes:
    @patch("ptt_scraper.feed.requests.get")
    def test_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = TWSE_SAMPLE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = _fetch_twse_quotes()
        assert len(result) == 2
        assert result[0] == {"code": "2330", "name": "台積電", "close": 1050.0}
        assert result[1] == {"code": "2317", "name": "鴻海", "close": 180.5}

    @patch("ptt_scraper.feed.requests.get")
    def test_empty_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = _fetch_twse_quotes()
        assert result == []

    @patch("ptt_scraper.feed.requests.get")
    def test_network_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("timeout")
        with pytest.raises(requests.RequestException):
            _fetch_twse_quotes()


# ------------------------------------------------------------------
# _fetch_tpex_quotes
# ------------------------------------------------------------------

TPEX_SAMPLE = [
    {"SecuritiesCompanyCode": "6547", "CompanyName": "高端疫苗", "Close": "35.20"},
    {"SecuritiesCompanyCode": "3105", "CompanyName": "穩懋", "Close": "250"},
]


class TestFetchTpexQuotes:
    @patch("ptt_scraper.feed.requests.get")
    def test_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = TPEX_SAMPLE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = _fetch_tpex_quotes()
        assert len(result) == 2
        assert result[0]["code"] == "6547"
        assert result[1]["close"] == 250.0


# ------------------------------------------------------------------
# compute_dynamic_aliases
# ------------------------------------------------------------------


class TestComputeDynamicAliases:
    @patch("ptt_scraper.feed._fetch_tpex_quotes")
    @patch("ptt_scraper.feed._fetch_twse_quotes")
    def test_normal(self, mock_twse, mock_tpex):
        mock_twse.return_value = [
            {"code": "2330", "name": "台積電", "close": 1050.0},
            {"code": "2317", "name": "鴻海", "close": 180.5},
        ]
        mock_tpex.return_value = [
            {"code": "6547", "name": "高端疫苗", "close": 35.2},
        ]

        aliases = compute_dynamic_aliases()
        assert aliases["股王"] == ["2330", "台積電"]
        assert aliases["股后"] == ["2317", "鴻海"]

    @patch("ptt_scraper.feed._fetch_tpex_quotes")
    @patch("ptt_scraper.feed._fetch_twse_quotes")
    def test_tpex_is_highest(self, mock_twse, mock_tpex):
        mock_twse.return_value = [
            {"code": "2330", "name": "台積電", "close": 500.0},
        ]
        mock_tpex.return_value = [
            {"code": "6510", "name": "精測", "close": 2000.0},
        ]

        aliases = compute_dynamic_aliases()
        assert aliases["股王"] == ["6510", "精測"]
        assert aliases["股后"] == ["2330", "台積電"]

    @patch("ptt_scraper.feed._fetch_tpex_quotes")
    @patch("ptt_scraper.feed._fetch_twse_quotes")
    def test_only_one_stock(self, mock_twse, mock_tpex):
        mock_twse.return_value = [
            {"code": "2330", "name": "台積電", "close": 1050.0},
        ]
        mock_tpex.return_value = []

        aliases = compute_dynamic_aliases()
        assert aliases["股王"] == ["2330", "台積電"]
        assert "股后" not in aliases

    @patch("ptt_scraper.feed._fetch_tpex_quotes")
    @patch("ptt_scraper.feed._fetch_twse_quotes")
    def test_both_fail(self, mock_twse, mock_tpex):
        mock_twse.side_effect = requests.RequestException("TWSE down")
        mock_tpex.side_effect = requests.RequestException("TPEX down")

        aliases = compute_dynamic_aliases()
        assert aliases == {}

    @patch("ptt_scraper.feed._fetch_tpex_quotes")
    @patch("ptt_scraper.feed._fetch_twse_quotes")
    def test_twse_fails_tpex_ok(self, mock_twse, mock_tpex):
        mock_twse.side_effect = requests.RequestException("TWSE down")
        mock_tpex.return_value = [
            {"code": "6510", "name": "精測", "close": 2000.0},
            {"code": "6547", "name": "高端", "close": 35.0},
        ]

        aliases = compute_dynamic_aliases()
        assert aliases["股王"] == ["6510", "精測"]
        assert aliases["股后"] == ["6547", "高端"]


# ------------------------------------------------------------------
# update_dynamic_aliases
# ------------------------------------------------------------------


class TestUpdateDynamicAliases:
    @patch("ptt_scraper.feed._fetch_tpex_quotes")
    @patch("ptt_scraper.feed._fetch_twse_quotes")
    def test_writes_json_file(self, mock_twse, mock_tpex, tmp_path):
        mock_twse.return_value = [
            {"code": "2330", "name": "台積電", "close": 1050.0},
            {"code": "2317", "name": "鴻海", "close": 180.5},
        ]
        mock_tpex.return_value = []

        # 暫時重導輸出路徑到 tmp_path
        fake_path = tmp_path / "dynamic_aliases.json"
        with (
            patch("ptt_scraper.feed.DYNAMIC_ALIASES_PATH", fake_path),
            patch("ptt_scraper.feed._DATA_DIR", tmp_path),
        ):
            result_path = update_dynamic_aliases()

        assert result_path == fake_path
        assert fake_path.exists()

        data = json.loads(fake_path.read_text(encoding="utf-8"))
        assert data["股王"] == ["2330", "台積電"]
        assert data["股后"] == ["2317", "鴻海"]
        assert "_updated_at" in data
        assert "_comment" in data

    @patch("ptt_scraper.feed._fetch_tpex_quotes")
    @patch("ptt_scraper.feed._fetch_twse_quotes")
    def test_writes_empty_when_both_fail(self, mock_twse, mock_tpex, tmp_path):
        mock_twse.side_effect = requests.RequestException("fail")
        mock_tpex.side_effect = requests.RequestException("fail")

        fake_path = tmp_path / "dynamic_aliases.json"
        with (
            patch("ptt_scraper.feed.DYNAMIC_ALIASES_PATH", fake_path),
            patch("ptt_scraper.feed._DATA_DIR", tmp_path),
        ):
            update_dynamic_aliases()

        data = json.loads(fake_path.read_text(encoding="utf-8"))
        assert "股王" not in data
        assert "_updated_at" in data
