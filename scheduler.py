#!/usr/bin/env python3
"""排程器 — 定時爬取 PTT / Reddit 並寫入 InfluxDB。

用法:
    python scheduler.py                         # 預設每 5 分鐘跑一次 (PTT)
    python scheduler.py --interval 10           # 每 10 分鐘
    python scheduler.py --board Stock --pages 2 # 自訂看板與頁數
    python scheduler.py --source reddit         # 爬 Reddit
    python scheduler.py --source both           # PTT + Reddit 雙源
    INFLUXDB_URL=http://myhost:8086 python scheduler.py  # 自訂 InfluxDB
"""

import argparse
import logging
import signal
import sys
import time

from ptt_scraper import (
    BuzzDetector,
    EntityMapper,
    PttScraper,
    SectorTracker,
    SentimentScorer,
    summarize_contrarian,
)
from ptt_scraper.store import InfluxStore
from reddit_scraper import RedditEntityMapper, RedditScraper, RedditSentimentScorer

logger = logging.getLogger(__name__)

# 重試設定
MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # 秒


def _run_with_retry(func, *args, **kwargs) -> None:
    """執行 func 並在失敗時以指數退避重試，最多 MAX_RETRIES 次。"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            func(*args, **kwargs)
            return
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.error("第 %d/%d 次嘗試失敗，跳過本輪: %s", attempt, MAX_RETRIES, exc)
                return
            wait = INITIAL_BACKOFF * (2 ** (attempt - 1))
            logger.warning(
                "第 %d/%d 次嘗試失敗: %s — %ds 後重試",
                attempt,
                MAX_RETRIES,
                exc,
                wait,
            )
            time.sleep(wait)


def run_ptt(board: str, pages: int, delay: float, store: InfluxStore) -> None:
    """執行一輪 PTT 爬取 + 分析 + 寫入。"""
    logger.info("開始爬取 PTT %s 版 (%d 頁)...", board, pages)

    scraper = PttScraper(board=board, delay=delay)
    posts = scraper.fetch_posts(max_pages=pages)

    if not posts:
        logger.info("PTT 未抓到文章，跳過本輪。")
        return

    logger.info("PTT 抓到 %d 篇文章，開始分析...", len(posts))
    output: dict = {}

    # 情緒分析
    scorer = SentimentScorer()
    mapper = EntityMapper()
    results = []
    for post in posts:
        sentiment = scorer.analyze_post(post)
        entities = mapper.find_entities(post.title + " " + post.content)
        results.append(
            {
                "title": post.title,
                "url": post.url,
                "author": post.author,
                "date": post.date,
                "sentiment": {
                    "score": sentiment.score,
                    "label": sentiment.label,
                    "push": sentiment.push_count,
                    "boo": sentiment.boo_count,
                    "arrow": sentiment.arrow_count,
                },
                "entities": entities,
            }
        )
    output["sentiment"] = results

    # 反指標
    summary = summarize_contrarian(posts)
    output["contrarian"] = {
        "total_posts": summary.total_posts,
        "capitulation_count": summary.capitulation_count,
        "euphoria_count": summary.euphoria_count,
        "capitulation_ratio": round(summary.capitulation_ratio, 4),
        "euphoria_ratio": round(summary.euphoria_ratio, 4),
        "market_signal": summary.market_signal,
    }

    # 異常熱度
    detector = BuzzDetector(mapper=mapper)
    report = detector.analyze(posts)
    detector.save_snapshot(posts)
    output["buzz"] = {
        "total_posts": report.total_posts,
        "tickers": [
            {
                "ticker": t.ticker,
                "name": t.name,
                "mentions": t.mention_count,
                "buzz_score": t.buzz_score,
                "anomaly": t.is_anomaly,
            }
            for t in report.tickers
        ],
    }

    # 板塊輪動
    tracker = SectorTracker()
    sector_report = tracker.analyze(posts)
    output["sectors"] = {
        "total_posts": sector_report.total_posts,
        "ranking": [
            {
                "sector": h.sector,
                "mentions": h.mention_count,
                "keywords": h.matched_keywords,
            }
            for h in sector_report.sectors
        ],
    }

    # 寫入 InfluxDB
    count = store.write_all(output, board, source="ptt")
    logger.info("PTT 已寫入 %d 筆資料到 InfluxDB。", count)

    # 簡要摘要
    bullish = sum(1 for r in results if r["sentiment"]["label"] == "bullish")
    bearish = sum(1 for r in results if r["sentiment"]["label"] == "bearish")
    logger.info(
        "PTT 情緒: 看多=%d 看空=%d | 反指標: %s | 熱門板塊: %s",
        bullish,
        bearish,
        summary.market_signal,
        sector_report.top_sector or "N/A",
    )


def run_reddit(
    subreddits: list[str] | None,
    limit: int,
    delay: float,
    store: InfluxStore,
) -> None:
    """執行一輪 Reddit 爬取 + 分析 + 寫入。"""
    scraper = RedditScraper(subreddits=subreddits, delay=delay)
    subs_str = ", ".join(scraper.subreddits)
    logger.info("開始爬取 Reddit [%s] (每版 %d 篇)...", subs_str, limit)

    posts = scraper.fetch_posts(limit=limit)

    if not posts:
        logger.info("Reddit 未抓到文章，跳過本輪。")
        return

    logger.info("Reddit 抓到 %d 篇文章，開始分析...", len(posts))
    output: dict = {}

    scorer = RedditSentimentScorer()
    mapper = RedditEntityMapper()
    results = []
    for post in posts:
        sentiment = scorer.analyze_post(post)
        entities = mapper.find_entities(post.title + " " + post.selftext)
        results.append(
            {
                "title": post.title,
                "url": post.url,
                "author": post.author,
                "subreddit": post.subreddit,
                "sentiment": {
                    "score": sentiment.score,
                    "label": sentiment.label,
                    "upvote_ratio": sentiment.upvote_ratio,
                    "post_score": sentiment.post_score,
                    "bullish_hits": sentiment.bullish_hits,
                    "bearish_hits": sentiment.bearish_hits,
                },
                "entities": entities,
            }
        )
    output["sentiment"] = results

    # 寫入 InfluxDB
    board_label = ",".join(scraper.subreddits)
    count = store.write_all(output, board_label, source="reddit")
    logger.info("Reddit 已寫入 %d 筆資料到 InfluxDB。", count)

    bullish = sum(1 for r in results if r["sentiment"]["label"] == "bullish")
    bearish = sum(1 for r in results if r["sentiment"]["label"] == "bearish")
    logger.info("Reddit 情緒: 看多=%d 看空=%d", bullish, bearish)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="即時監控排程器 — 定時爬取 PTT / Reddit 並寫入 InfluxDB",
    )
    parser.add_argument(
        "--source",
        choices=["ptt", "reddit", "both"],
        default="ptt",
        help="資料源 (預設: ptt)",
    )
    parser.add_argument(
        "--board",
        default="Stock",
        help="PTT 目標看板 (預設: Stock)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="PTT 每輪爬幾頁 (預設: 1)",
    )
    parser.add_argument(
        "--subreddits",
        nargs="+",
        default=None,
        help="Reddit subreddit 列表",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Reddit 每版抓幾篇 (預設: 25)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="HTTP 請求間隔秒數 (預設: 0.5)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="排程間隔分鐘數 (預設: 5)",
    )
    args = parser.parse_args()

    # 設定 logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    store = InfluxStore()

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("收到中斷信號，正在關閉...")
        store.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    sources = []
    if args.source in ("ptt", "both"):
        sources.append("ptt")
    if args.source in ("reddit", "both"):
        sources.append("reddit")

    logger.info("即時監控已啟動")
    logger.info("  資料源: %s", ", ".join(sources))
    if "ptt" in sources:
        logger.info("  PTT 看板: %s, 頁數: %d", args.board, args.pages)
    if "reddit" in sources:
        subs = args.subreddits or ["(default 7 subs)"]
        logger.info("  Reddit: %s, 每版 %d 篇", ", ".join(subs), args.limit)
    logger.info("  間隔: 每 %d 分鐘", args.interval)
    logger.info("  InfluxDB: %s", store.client.url)
    logger.info("按 Ctrl+C 停止。")

    while True:
        if "ptt" in sources:
            _run_with_retry(run_ptt, args.board, args.pages, args.delay, store)
        if "reddit" in sources:
            reddit_delay = max(args.delay, 1.0)  # Reddit 至少 1s
            _run_with_retry(run_reddit, args.subreddits, args.limit, reddit_delay, store)

        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
