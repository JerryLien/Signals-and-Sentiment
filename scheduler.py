#!/usr/bin/env python3
"""排程器 — 定時爬取 PTT 並寫入 InfluxDB。

用法:
    python scheduler.py                         # 預設每 5 分鐘跑一次
    python scheduler.py --interval 10           # 每 10 分鐘
    python scheduler.py --board Stock --pages 2 # 自訂看板與頁數
    INFLUXDB_URL=http://myhost:8086 python scheduler.py  # 自訂 InfluxDB
"""

import argparse
import signal
import sys
import time
from datetime import datetime

from ptt_scraper import (
    BuzzDetector,
    EntityMapper,
    PttScraper,
    SectorTracker,
    SentimentScorer,
    summarize_contrarian,
)
from ptt_scraper.store import InfluxStore


def run_once(board: str, pages: int, delay: float, store: InfluxStore) -> None:
    """執行一輪完整的爬取 + 分析 + 寫入。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{ts}] 開始爬取 PTT {board} 版 ({pages} 頁)...")

    scraper = PttScraper(board=board, delay=delay)
    posts = scraper.fetch_posts(max_pages=pages)

    if not posts:
        print(f"[{ts}] 未抓到文章，跳過本輪。")
        return

    print(f"[{ts}] 抓到 {len(posts)} 篇文章，開始分析...")
    output: dict = {}

    # 情緒分析
    scorer = SentimentScorer()
    mapper = EntityMapper()
    results = []
    for post in posts:
        sentiment = scorer.analyze_post(post)
        entities = mapper.find_entities(post.title + " " + post.content)
        results.append({
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
        })
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
    count = store.write_all(output, board)
    print(f"[{ts}] 已寫入 {count} 筆資料到 InfluxDB。")

    # 簡要摘要
    bullish = sum(1 for r in results if r["sentiment"]["label"] == "bullish")
    bearish = sum(1 for r in results if r["sentiment"]["label"] == "bearish")
    print(f"[{ts}] 情緒: 看多={bullish} 看空={bearish} | "
          f"反指標: {summary.market_signal} | "
          f"熱門板塊: {sector_report.top_sector or 'N/A'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PTT 即時監控排程器 — 定時爬取並寫入 InfluxDB",
    )
    parser.add_argument(
        "--board", default="Stock", help="目標看板 (預設: Stock)",
    )
    parser.add_argument(
        "--pages", type=int, default=1, help="每輪爬幾頁 (預設: 1)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5, help="HTTP 請求間隔秒數 (預設: 0.5)",
    )
    parser.add_argument(
        "--interval", type=int, default=5, help="排程間隔分鐘數 (預設: 5)",
    )
    args = parser.parse_args()

    store = InfluxStore()

    # Graceful shutdown
    def shutdown(signum, frame):
        print("\n收到中斷信號，正在關閉...")
        store.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"PTT 即時監控已啟動")
    print(f"  看板: {args.board}")
    print(f"  頁數: {args.pages}")
    print(f"  間隔: 每 {args.interval} 分鐘")
    print(f"  InfluxDB: {store.client.url}")
    print(f"按 Ctrl+C 停止。\n")

    while True:
        try:
            run_once(args.board, args.pages, args.delay, store)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] [ERROR] {exc}")

        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
