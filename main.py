#!/usr/bin/env python3
"""PTT 股板情緒分析 — 受 ICE Reddit Signals and Sentiment 啟發。

用法:
    python main.py                      # 預設爬 Stock 版 1 頁
    python main.py --board Gossiping --pages 3
"""

import argparse
import json
import sys

from ptt_scraper import EntityMapper, PttScraper, SentimentScorer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PTT Signals and Sentiment — 爬取 PTT 文章並分析情緒",
    )
    parser.add_argument(
        "--board", default="Stock", help="目標看板 (預設: Stock)",
    )
    parser.add_argument(
        "--pages", type=int, default=1, help="要爬幾頁 (預設: 1)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5, help="每次請求間隔秒數 (預設: 0.5)",
    )
    parser.add_argument(
        "--json", action="store_true", help="以 JSON 格式輸出結果",
    )
    args = parser.parse_args()

    scraper = PttScraper(board=args.board, delay=args.delay)
    scorer = SentimentScorer()
    mapper = EntityMapper()

    print(f"正在爬取 PTT {args.board} 版 (共 {args.pages} 頁)...\n")
    posts = scraper.fetch_posts(max_pages=args.pages)

    if not posts:
        print("未抓到任何文章。")
        sys.exit(0)

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

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_table(results)


def _print_table(results: list[dict]) -> None:
    """以易讀的表格方式印出結果。"""
    print(f"{'標題':<40} {'情緒':>8} {'推':>4} {'噓':>4} {'→':>4} {'相關標的'}")
    print("-" * 90)
    for r in results:
        s = r["sentiment"]
        title = r["title"][:38]
        entities_str = ", ".join(
            f"{e['ticker']}({e['name']})" if e["name"] else e["ticker"]
            for e in r["entities"]
        )
        label = {
            "bullish": "🟢看多",
            "bearish": "🔴看空",
            "neutral": "⚪中性",
        }.get(s["label"], s["label"])

        print(
            f"{title:<40} {label:>8} {s['push']:>4} {s['boo']:>4} {s['arrow']:>4} {entities_str}"
        )

    # 總結
    total = len(results)
    bullish = sum(1 for r in results if r["sentiment"]["label"] == "bullish")
    bearish = sum(1 for r in results if r["sentiment"]["label"] == "bearish")
    neutral = total - bullish - bearish
    print("-" * 90)
    print(f"共 {total} 篇 | 看多: {bullish} | 看空: {bearish} | 中性: {neutral}")


if __name__ == "__main__":
    main()
