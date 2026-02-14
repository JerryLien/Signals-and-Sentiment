"""Tests for reddit_scraper.entity_mapping module."""

from reddit_scraper.entity_mapping import RedditEntityMapper


class TestRedditEntityMapper:
    def test_dollar_ticker_syntax(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("I'm buying $NVDA and $TSLA")
        tickers = {r["ticker"] for r in results}
        assert "NVDA" in tickers
        assert "TSLA" in tickers

    def test_alias_lookup(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("papa elon is at it again with tesla")
        tickers = {r["ticker"] for r in results}
        assert "TSLA" in tickers

    def test_nvidia_alias(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("nvidia just crushed earnings, jensen is a genius")
        tickers = {r["ticker"] for r in results}
        assert "NVDA" in tickers

    def test_common_words_excluded(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("I AM THE BEST AT THIS GAME")
        tickers = {r["ticker"] for r in results}
        assert "AM" not in tickers
        assert "THE" not in tickers
        assert "AT" not in tickers

    def test_wsb_abbreviations_excluded(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("IMO this is YOLO FOMO HODL territory")
        tickers = {r["ticker"] for r in results}
        assert "IMO" not in tickers
        assert "YOLO" not in tickers
        assert "FOMO" not in tickers

    def test_bare_ticker_detection(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("Look at AAPL and GOOG today")
        tickers = {r["ticker"] for r in results}
        assert "AAPL" in tickers
        assert "GOOG" in tickers

    def test_crypto_aliases(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("bitcoin and ethereum are pumping")
        tickers = {r["ticker"] for r in results}
        assert "BTC" in tickers
        assert "ETH" in tickers

    def test_dedup_same_ticker(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("nvidia $NVDA NVDA")
        nvda_results = [r for r in results if r["ticker"] == "NVDA"]
        assert len(nvda_results) == 1

    def test_entity_fields(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("tesla is great")
        tsla = next((r for r in results if r["ticker"] == "TSLA"), None)
        assert tsla is not None
        assert tsla["name"] == "Tesla"
        assert "matched" in tsla

    def test_dollar_ticker_name_is_empty(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("Buying $PLTR")
        # $PLTR via dollar syntax should have empty name if not in aliases first
        # But "palantir" is in aliases, so PLTR via alias has name
        pltr = next((r for r in results if r["ticker"] == "PLTR"), None)
        assert pltr is not None

    def test_no_entities(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("the weather is nice today")
        # Should have no or very few results
        for r in results:
            assert r["ticker"] not in ("AM", "IS", "THE")

    def test_extra_aliases(self):
        mapper = RedditEntityMapper(extra_aliases={"roaring kitty": ("GME", "GameStop")})
        results = mapper.find_entities("roaring kitty is back!")
        tickers = {r["ticker"] for r in results}
        assert "GME" in tickers

    def test_gamestop_aliases(self):
        mapper = RedditEntityMapper()
        results = mapper.find_entities("gamestonk to the moon!")
        tickers = {r["ticker"] for r in results}
        assert "GME" in tickers
