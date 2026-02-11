"""Tests for ptt_scraper.feed module."""

from ptt_scraper.feed import _parse_price


class TestParsePrice:
    def test_normal_price(self):
        assert _parse_price("123.45") == 123.45

    def test_price_with_comma(self):
        assert _parse_price("1,234.56") == 1234.56

    def test_invalid_price(self):
        assert _parse_price("N/A") is None

    def test_empty_string(self):
        assert _parse_price("") is None

    def test_none_input(self):
        assert _parse_price(None) is None

    def test_integer_price(self):
        assert _parse_price("500") == 500.0
