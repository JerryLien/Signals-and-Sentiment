"""Tests for ptt_scraper.entity_mapping module."""

from ptt_scraper.entity_mapping import EntityMapper


class TestEntityMapper:
    def test_find_ticker_by_alias(self):
        mapper = EntityMapper()
        results = mapper.find_entities("護國神山今天又漲了")
        tickers = {r["ticker"] for r in results}
        assert "2330" in tickers

    def test_find_ticker_by_number(self):
        mapper = EntityMapper()
        results = mapper.find_entities("2330今天收盤價很高")
        tickers = {r["ticker"] for r in results}
        assert "2330" in tickers

    def test_find_ticker_with_tw_suffix(self):
        mapper = EntityMapper()
        results = mapper.find_entities("看好2330.TW後續走勢")
        tickers = {r["ticker"] for r in results}
        assert "2330" in tickers

    def test_case_insensitive_alias(self):
        mapper = EntityMapper()
        results = mapper.find_entities("TSMC is great")
        tickers = {r["ticker"] for r in results}
        assert "2330" in tickers

    def test_multiple_entities(self):
        mapper = EntityMapper()
        results = mapper.find_entities("台積電跟鴻海都漲了")
        tickers = {r["ticker"] for r in results}
        assert "2330" in tickers
        assert "2317" in tickers

    def test_no_entities(self):
        mapper = EntityMapper()
        results = mapper.find_entities("今天天氣真好")
        # Should not find stock entities in non-stock text
        # (unless there happens to be a 4-digit number)
        for r in results:
            assert r["ticker"] not in ("2330", "2317")

    def test_dedup_same_ticker(self):
        mapper = EntityMapper()
        results = mapper.find_entities("台積電 tsmc 2330 gg 都是同一家")
        ticker_2330 = [r for r in results if r["ticker"] == "2330"]
        assert len(ticker_2330) == 1  # deduplicated

    def test_extra_aliases(self):
        mapper = EntityMapper(extra_aliases={"我的股票": ("9999", "測試公司")})
        results = mapper.find_entities("我的股票漲停了")
        tickers = {r["ticker"] for r in results}
        assert "9999" in tickers

    def test_numeric_ticker_not_match_short(self):
        mapper = EntityMapper()
        # 3-digit numbers should not match (pattern requires 4-6 digits)
        results = mapper.find_entities("只有123不是股票代碼")
        tickers = {r["ticker"] for r in results}
        assert "123" not in tickers

    def test_entity_has_correct_fields(self):
        mapper = EntityMapper()
        results = mapper.find_entities("護國神山")
        assert len(results) >= 1
        entity = next(r for r in results if r["ticker"] == "2330")
        assert "ticker" in entity
        assert "name" in entity
        assert "matched" in entity
        assert entity["name"] == "台積電"

    def test_numeric_ticker_has_empty_name(self):
        mapper = EntityMapper()
        results = mapper.find_entities("看看5876的表現")
        entity = next((r for r in results if r["ticker"] == "5876"), None)
        assert entity is not None
        assert entity["name"] == ""
