"""InfluxDB 寫入模組 — 把分析結果轉為時間序列資料。

同時支援 PTT 和 Reddit 兩種資料源，統一寫入同一個 InfluxDB bucket，
透過 source tag 區分來源，供 Grafana 即時視覺化。

Measurements:
- post_sentiment   : 每篇文章的情緒分數 (per-post)
- board_sentiment  : 看板/subreddit 整體情緒彙總 (per-scrape)
- contrarian_index : 畢業文/歐印文指數 (per-scrape, PTT only)
- ticker_buzz      : 個股討論熱度 (per-ticker per-scrape)
- sector_heat      : 板塊熱度 (per-sector per-scrape, PTT only)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)

# 預設連線參數（可透過環境變數覆寫）
INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "ptt-dev-token")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "ptt-lab")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "ptt_sentiment")


def validate_influxdb_env() -> list[str]:
    """檢查 InfluxDB 必要環境變數是否設定。

    Returns
    -------
    list[str]
        缺少的環境變數名稱。空列表表示全部都有。
    """
    required = ["INFLUXDB_TOKEN", "INFLUXDB_ORG", "INFLUXDB_BUCKET"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        logger.warning(
            "以下 InfluxDB 環境變數未設定，使用預設值: %s",
            ", ".join(missing),
        )
    return missing


class InfluxStore:
    """將分析結果寫入 InfluxDB 2.x。

    Parameters
    ----------
    url, token, org, bucket : str
        InfluxDB 連線參數，預設讀取環境變數或使用 docker-compose 預設值。
    """

    def __init__(
        self,
        url: str = INFLUXDB_URL,
        token: str = INFLUXDB_TOKEN,
        org: str = INFLUXDB_ORG,
        bucket: str = INFLUXDB_BUCKET,
    ):
        self.org = org
        self.bucket = bucket
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def close(self) -> None:
        self.client.close()

    # ------------------------------------------------------------------
    # 寫入方法
    # ------------------------------------------------------------------

    def write_sentiment(
        self,
        results: list[dict],
        board: str,
        source: str = "ptt",
    ) -> int:
        """寫入每篇文章的情緒分數 + 看板彙總。

        同時支援 PTT (push/boo/arrow) 和 Reddit (upvote_ratio/bullish_hits) 格式。
        """
        now = datetime.now(tz=timezone.utc)
        points: list[Point] = []

        total_score = 0.0
        bullish = bearish = neutral = 0

        for r in results:
            s = r["sentiment"]
            total_score += s["score"]
            if s["label"] == "bullish":
                bullish += 1
            elif s["label"] == "bearish":
                bearish += 1
            else:
                neutral += 1

            # per-post
            p = (
                Point("post_sentiment")
                .tag("source", source)
                .tag("board", board)
                .tag("label", s["label"])
                .field("score", float(s["score"]))
                .field("title", r["title"])
                .time(now)
            )

            # PTT-specific fields
            if "push" in s:
                p = p.field("push", s["push"])
                p = p.field("boo", s["boo"])
                p = p.field("arrow", s["arrow"])

            # Reddit-specific fields
            if "upvote_ratio" in s:
                p = p.field("upvote_ratio", float(s["upvote_ratio"]))
                p = p.field("post_score", s["post_score"])
                p = p.field("bullish_hits", s["bullish_hits"])
                p = p.field("bearish_hits", s["bearish_hits"])
                if r.get("subreddit"):
                    p = p.tag("subreddit", r["subreddit"])

            # 附加第一個 entity 作為 tag (方便 GROUP BY ticker)
            if r.get("entities"):
                p = p.tag("ticker", r["entities"][0]["ticker"])
            points.append(p)

        # board-level summary
        count = len(results)
        avg_score = total_score / count if count else 0.0
        points.append(
            Point("board_sentiment")
            .tag("source", source)
            .tag("board", board)
            .field("avg_score", round(avg_score, 2))
            .field("total_posts", count)
            .field("bullish", bullish)
            .field("bearish", bearish)
            .field("neutral", neutral)
            .time(now)
        )

        self.write_api.write(bucket=self.bucket, org=self.org, record=points)
        return len(points)

    def write_contrarian(
        self,
        data: dict,
        board: str,
        source: str = "ptt",
    ) -> int:
        """寫入反指標指數。"""
        now = datetime.now(tz=timezone.utc)
        p = (
            Point("contrarian_index")
            .tag("source", source)
            .tag("board", board)
            .tag("market_signal", data["market_signal"])
            .field("total_posts", data["total_posts"])
            .field("capitulation_count", data["capitulation_count"])
            .field("euphoria_count", data["euphoria_count"])
            .field("capitulation_ratio", float(data["capitulation_ratio"]))
            .field("euphoria_ratio", float(data["euphoria_ratio"]))
            .time(now)
        )
        self.write_api.write(bucket=self.bucket, org=self.org, record=p)
        return 1

    def write_buzz(
        self,
        data: dict,
        board: str,
        source: str = "ptt",
    ) -> int:
        """寫入個股討論熱度。"""
        now = datetime.now(tz=timezone.utc)
        points: list[Point] = []

        for t in data["tickers"]:
            p = (
                Point("ticker_buzz")
                .tag("source", source)
                .tag("board", board)
                .tag("ticker", t["ticker"])
                .tag("anomaly", str(t["anomaly"]).lower())
                .field("name", t["name"])
                .field("mentions", t["mentions"])
                .field("buzz_score", float(t["buzz_score"]))
                .time(now)
            )
            points.append(p)

        self.write_api.write(bucket=self.bucket, org=self.org, record=points)
        return len(points)

    def write_sectors(
        self,
        data: dict,
        board: str,
        source: str = "ptt",
    ) -> int:
        """寫入板塊熱度。"""
        now = datetime.now(tz=timezone.utc)
        points: list[Point] = []

        for rank, s in enumerate(data["ranking"], 1):
            p = (
                Point("sector_heat")
                .tag("source", source)
                .tag("board", board)
                .tag("sector", s["sector"])
                .field("mentions", s["mentions"])
                .field("rank", rank)
                .field("keywords", ", ".join(s.get("keywords", [])))
                .time(now)
            )
            points.append(p)

        self.write_api.write(bucket=self.bucket, org=self.org, record=points)
        return len(points)

    def write_all(
        self,
        output: dict,
        board: str,
        source: str = "ptt",
    ) -> int:
        """一次寫入所有可用的分析結果。

        Parameters
        ----------
        source : str
            資料來源標記，"ptt" 或 "reddit"。
        """
        total = 0
        if "sentiment" in output:
            total += self.write_sentiment(output["sentiment"], board, source)
        if "contrarian" in output:
            total += self.write_contrarian(output["contrarian"], board, source)
        if "buzz" in output:
            total += self.write_buzz(output["buzz"], board, source)
        if "sectors" in output:
            total += self.write_sectors(output["sectors"], board, source)
        return total
