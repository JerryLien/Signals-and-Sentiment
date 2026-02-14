"""環境變數驗證的測試。"""

from unittest.mock import patch

from ptt_scraper.store import validate_influxdb_env


class TestValidateInfluxdbEnv:
    @patch.dict(
        "os.environ",
        {"INFLUXDB_TOKEN": "tok", "INFLUXDB_ORG": "org", "INFLUXDB_BUCKET": "bkt"},
    )
    def test_all_set(self):
        missing = validate_influxdb_env()
        assert missing == []

    @patch.dict("os.environ", {}, clear=True)
    def test_all_missing(self):
        missing = validate_influxdb_env()
        assert "INFLUXDB_TOKEN" in missing
        assert "INFLUXDB_ORG" in missing
        assert "INFLUXDB_BUCKET" in missing

    @patch.dict(
        "os.environ",
        {"INFLUXDB_TOKEN": "tok", "INFLUXDB_ORG": "", "INFLUXDB_BUCKET": "bkt"},
    )
    def test_partial_empty(self):
        missing = validate_influxdb_env()
        assert "INFLUXDB_ORG" in missing
        assert "INFLUXDB_TOKEN" not in missing
