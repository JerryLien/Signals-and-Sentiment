"""異常討論熱度偵測 — 市場監控與 Pump-and-Dump 早期預警。

核心概念:
- 統計每支股票被提及的次數 (mention count)
- 計算「Buzz Score」: 本批次提及量 vs. 歷史基線的標準差倍數
- 標記異常飆升的標的，作為 Pump-and-Dump 潛在訊號
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from ptt_scraper.entity_mapping import EntityMapper
from ptt_scraper.scraper import Post

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_BUZZ_HISTORY_PATH = _DATA_DIR / "buzz_history.json"
_TW_TZ = timezone(timedelta(hours=8))


@dataclass
class TickerBuzz:
    """單一標的的討論熱度。"""

    ticker: str
    name: str
    mention_count: int
    buzz_score: float  # 相對歷史基線的標準差倍數
    is_anomaly: bool  # buzz_score >= threshold


@dataclass
class BuzzReport:
    """一批文章的討論熱度報告。"""

    total_posts: int
    tickers: list[TickerBuzz]
    anomalies: list[TickerBuzz]


class BuzzDetector:
    """偵測個股的異常討論熱度。

    Parameters
    ----------
    mapper : EntityMapper
        實體辨識器，用來從文章中抓出股票代碼。
    anomaly_threshold : float
        Buzz score (Z-score) 超過此值視為異常，預設 2.0。
    history_window : int
        保留幾期歷史資料用於計算基線，預設 30。
    """

    def __init__(
        self,
        mapper: EntityMapper | None = None,
        anomaly_threshold: float = 2.0,
        history_window: int = 30,
    ):
        self.mapper = mapper or EntityMapper()
        self.anomaly_threshold = anomaly_threshold
        self.history_window = history_window
        self.history = self._load_history()

    # ------------------------------------------------------------------
    # 公開方法
    # ------------------------------------------------------------------

    def analyze(self, posts: list[Post]) -> BuzzReport:
        """分析一批文章的個股討論熱度。"""
        # 計算每支股票的提及次數
        mention_counter: Counter[str] = Counter()
        ticker_names: dict[str, str] = {}

        for post in posts:
            text = post.title + " " + post.content
            for c in post.comments:
                text += " " + c.content
            entities = self.mapper.find_entities(text)
            for e in entities:
                ticker = e["ticker"]
                mention_counter[ticker] += 1
                if e["name"] and ticker not in ticker_names:
                    ticker_names[ticker] = e["name"]

        # 計算 buzz score
        tickers: list[TickerBuzz] = []
        for ticker, count in mention_counter.most_common():
            score = self._compute_buzz_score(ticker, count)
            tickers.append(
                TickerBuzz(
                    ticker=ticker,
                    name=ticker_names.get(ticker, ""),
                    mention_count=count,
                    buzz_score=round(score, 2),
                    is_anomaly=score >= self.anomaly_threshold,
                )
            )

        anomalies = [t for t in tickers if t.is_anomaly]

        return BuzzReport(
            total_posts=len(posts),
            tickers=tickers,
            anomalies=anomalies,
        )

    def save_snapshot(self, posts: list[Post]) -> None:
        """將本次的提及次數存入歷史，供未來計算基線。"""
        mention_counter: Counter[str] = Counter()
        for post in posts:
            text = post.title + " " + post.content
            entities = self.mapper.find_entities(text)
            for e in entities:
                mention_counter[e["ticker"]] += 1

        now = datetime.now(tz=_TW_TZ).isoformat(timespec="seconds")
        snapshot = {"date": now, "mentions": dict(mention_counter)}

        self.history.append(snapshot)
        # 只保留最近 N 期
        self.history = self.history[-self.history_window :]
        self._save_history()

    # ------------------------------------------------------------------
    # 內部方法
    # ------------------------------------------------------------------

    def _compute_buzz_score(self, ticker: str, current_count: int) -> float:
        """計算 Z-score: (當前值 - 歷史平均) / 歷史標準差。"""
        historical_counts = [snap["mentions"].get(ticker, 0) for snap in self.history]

        if len(historical_counts) < 2:
            # 歷史資料不足，無法計算有意義的 Z-score
            # 有提及就給正分，讓冷門股初次出現能被注意到
            return float(current_count) if current_count > 0 else 0.0

        mean = sum(historical_counts) / len(historical_counts)
        variance = sum((x - mean) ** 2 for x in historical_counts) / len(historical_counts)
        std = math.sqrt(variance)

        if std == 0:
            # 歷史值全部相同
            return float(current_count - mean) if current_count != mean else 0.0

        return (current_count - mean) / std

    def _load_history(self) -> list[dict]:
        if not _BUZZ_HISTORY_PATH.exists():
            return []
        with open(_BUZZ_HISTORY_PATH, encoding="utf-8") as f:
            return json.load(f)

    def _save_history(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_BUZZ_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)
