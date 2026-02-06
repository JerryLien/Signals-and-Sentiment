#!/usr/bin/env python3
"""AnomalyMonitor — 定時輪詢 InfluxDB 偵測異常，觸發 LLM 解釋 + Grafana 標註。

兩種偵測模式：
1. Buzz Z-score > threshold → 個股討論量暴增
2. Sentiment Premium 突破 ±threshold → 跨市場情緒分歧

去重機制：同一 (event_type, ticker) 在 cooldown 時間內不重複觸發。
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime

from influxdb_client import InfluxDBClient

from llm_agent.config import LLMConfig
from llm_agent.explainer import AnomalyEvent, AnomalyExplainer
from llm_agent.annotator import GrafanaAnnotator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("llm-agent")


class AnomalyMonitor:
    """主迴圈：輪詢 InfluxDB → 偵測異常 → LLM 解釋 → Grafana 標註。"""

    def __init__(self, config: LLMConfig | None = None):
        self.cfg = config or LLMConfig()
        self._influx = InfluxDBClient(
            url=self.cfg.INFLUXDB_URL,
            token=self.cfg.INFLUXDB_TOKEN,
            org=self.cfg.INFLUXDB_ORG,
        )
        self._query_api = self._influx.query_api()
        self._explainer = AnomalyExplainer(self.cfg)
        self._annotator = GrafanaAnnotator(self.cfg)

        # 去重: {(event_type, ticker): last_trigger_epoch}
        self._seen: dict[tuple[str, str], float] = {}

    def close(self) -> None:
        self._influx.close()
        self._explainer.close()

    # ── Dedup ──────────────────────────────────────────────

    def _is_new(self, event_type: str, ticker: str) -> bool:
        """檢查此事件是否在冷卻期外。"""
        key = (event_type, ticker)
        last = self._seen.get(key, 0)
        if time.time() - last < self.cfg.DEDUP_COOLDOWN:
            return False
        self._seen[key] = time.time()
        return True

    # ── Detector 1: Buzz Z-score ───────────────────────────

    def _detect_buzz_anomalies(self) -> list[AnomalyEvent]:
        """查詢最近 N 分鐘內 Z-score 超標的 ticker。"""
        lookback = self.cfg.LOOKBACK_MINUTES
        threshold = self.cfg.BUZZ_ZSCORE_THRESHOLD

        flux = f"""
from(bucket: "{self.cfg.INFLUXDB_BUCKET}")
  |> range(start: -{lookback}m)
  |> filter(fn: (r) => r._measurement == "ticker_buzz")
  |> filter(fn: (r) => r._field == "buzz_score")
  |> filter(fn: (r) => r._value >= {threshold})
  |> group(columns: ["ticker", "source"])
  |> last()
"""
        events: list[AnomalyEvent] = []
        try:
            tables = self._query_api.query(flux)
            for table in tables:
                for record in table.records:
                    ticker = record.values.get("ticker", "")
                    source = record.values.get("source", "")
                    value = float(record.get_value())

                    if not self._is_new("buzz_zscore", ticker):
                        logger.debug("Dedup skip: buzz_zscore %s", ticker)
                        continue

                    events.append(AnomalyEvent(
                        event_type="buzz_zscore",
                        ticker=ticker,
                        source=source,
                        value=value,
                        titles=[],
                    ))
        except Exception as exc:
            logger.warning("Buzz anomaly query failed: %s", exc)

        return events

    # ── Detector 2: Sentiment Premium ──────────────────────

    def _detect_premium_breakouts(self) -> list[AnomalyEvent]:
        """查詢最近 N 分鐘內 Sentiment Premium 突破 ±threshold 的事件。

        使用與 Grafana Panel 11 相同的 Flux join 邏輯。
        """
        lookback = self.cfg.LOOKBACK_MINUTES
        threshold = self.cfg.PREMIUM_THRESHOLD

        flux = f"""
import "math"

ptt = from(bucket: "{self.cfg.INFLUXDB_BUCKET}")
  |> range(start: -{lookback}m)
  |> filter(fn: (r) => r._measurement == "post_sentiment"
      and r.source == "ptt" and r.ticker == "2330"
      and r._field == "score")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value"])

reddit = from(bucket: "{self.cfg.INFLUXDB_BUCKET}")
  |> range(start: -{lookback}m)
  |> filter(fn: (r) => r._measurement == "post_sentiment"
      and r.source == "reddit" and r.ticker == "TSM"
      and r._field == "score")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value"])

join(tables: {{ptt: ptt, reddit: reddit}}, on: ["_time"])
  |> map(fn: (r) => ({{_time: r._time, _value: r._value_reddit - r._value_ptt}}))
  |> filter(fn: (r) => math.abs(x: r._value) >= {threshold})
  |> last()
"""
        events: list[AnomalyEvent] = []
        try:
            tables = self._query_api.query(flux)
            for table in tables:
                for record in table.records:
                    value = float(record.get_value())
                    ticker = "TSM/2330"

                    if not self._is_new("premium_breakout", ticker):
                        logger.debug("Dedup skip: premium_breakout %s", ticker)
                        continue

                    events.append(AnomalyEvent(
                        event_type="premium_breakout",
                        ticker=ticker,
                        source="cross",
                        value=value,
                        titles=[],
                    ))
        except Exception as exc:
            logger.warning("Premium breakout query failed: %s", exc)

        return events

    # ── Main Loop ──────────────────────────────────────────

    def run_once(self) -> int:
        """執行一輪偵測 + 解釋 + 標註。回傳處理的事件數。"""
        events = self._detect_buzz_anomalies() + self._detect_premium_breakouts()

        if not events:
            logger.debug("No anomalies detected.")
            return 0

        count = 0
        for event in events:
            logger.info(
                "Anomaly detected: %s %s (value=%.2f, source=%s)",
                event.event_type, event.ticker, event.value, event.source,
            )

            # 撈貼文 + LLM 解釋
            if event.source == "cross":
                # 跨市場事件：撈兩邊的貼文
                titles_ptt = self._explainer.query_top_posts("2330", "ptt", 30, 5)
                titles_reddit = self._explainer.query_top_posts("TSM", "reddit", 30, 5)
                event.titles = titles_reddit + titles_ptt
            else:
                event.titles = self._explainer.query_top_posts(
                    event.ticker, event.source, 30, 10,
                )

            explanation = self._explainer.explain(event)
            logger.info("LLM explanation: %s", explanation.summary)

            # 寫入 Grafana Annotation
            self._annotator.annotate(explanation)
            count += 1

        return count

    def run_forever(self) -> None:
        """持續執行，每隔 POLL_INTERVAL 秒偵測一次。"""
        logger.info("LLM Agent 異常偵測已啟動")
        logger.info("  Provider: %s (%s)", self.cfg.LLM_PROVIDER, self.cfg.LLM_MODEL)
        logger.info("  Buzz threshold: Z-score >= %.1f", self.cfg.BUZZ_ZSCORE_THRESHOLD)
        logger.info("  Premium threshold: |premium| >= %.1f", self.cfg.PREMIUM_THRESHOLD)
        logger.info("  Poll interval: %ds", self.cfg.POLL_INTERVAL)
        logger.info("  Dedup cooldown: %ds", self.cfg.DEDUP_COOLDOWN)
        logger.info("  InfluxDB: %s", self.cfg.INFLUXDB_URL)
        logger.info("  Grafana: %s", self.cfg.GRAFANA_URL)

        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.error("Monitor error: %s", exc)

            time.sleep(self.cfg.POLL_INTERVAL)


# ── CLI ────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM Agent — 異常事件自動歸因 (The 'Why' Layer)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="只跑一次偵測（測試用）",
    )
    args = parser.parse_args()

    monitor = AnomalyMonitor()

    def shutdown(signum, frame):
        logger.info("收到中斷信號，正在關閉...")
        monitor.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if args.once:
        count = monitor.run_once()
        logger.info("偵測完成，處理了 %d 筆異常事件。", count)
        monitor.close()
    else:
        monitor.run_forever()


if __name__ == "__main__":
    main()
