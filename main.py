#!/usr/bin/env python3
"""PTT / Reddit 情緒分析 — 受 ICE Reddit Signals and Sentiment 啟發。

用法:
    python main.py                              # PTT 基本情緒分析（預設）
    python main.py --all --pages 5              # PTT 全部分析
    python main.py --source reddit              # Reddit 美股/加密貨幣情緒
    python main.py --source reddit --subreddits wallstreetbets cryptocurrency
    python main.py --all --influxdb             # 全部分析 + 寫入 InfluxDB
"""

import argparse
import json
import sys

from ptt_scraper import (
    BuzzDetector,
    EntityMapper,
    InfluxStore,
    PttScraper,
    SectorTracker,
    SentimentScorer,
    summarize_contrarian,
    update_dynamic_aliases,
)
from reddit_scraper import RedditEntityMapper, RedditScraper, RedditSentimentScorer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Signals and Sentiment — PTT / Reddit 情緒分析",
    )
    # 資料源
    parser.add_argument(
        "--source", choices=["ptt", "reddit"], default="ptt",
        help="資料源 (預設: ptt)",
    )
    # PTT 參數
    parser.add_argument(
        "--board", default="Stock", help="PTT 看板 (預設: Stock)",
    )
    parser.add_argument(
        "--pages", type=int, default=1, help="PTT 往前爬幾頁 (預設: 1)",
    )
    # Reddit 參數
    parser.add_argument(
        "--subreddits", nargs="+", default=None,
        help="Reddit subreddit 列表 (預設: wallstreetbets stocks investing cryptocurrency bitcoin)",
    )
    parser.add_argument(
        "--limit", type=int, default=25,
        help="Reddit 每個 subreddit 抓幾篇 (預設: 25, 上限 100)",
    )
    parser.add_argument(
        "--comments", action="store_true",
        help="Reddit: 是否進入文章抓留言 (較慢但更準確)",
    )
    # 共用參數
    parser.add_argument(
        "--delay", type=float, default=None,
        help="每次請求間隔秒數 (PTT 預設 0.5, Reddit 預設 1.0)",
    )
    parser.add_argument(
        "--json", action="store_true", help="以 JSON 格式輸出結果",
    )
    parser.add_argument(
        "--update-aliases", action="store_true",
        help="PTT: 從 TWSE/TPEX 更新動態暱稱（股王、股后等）",
    )
    parser.add_argument(
        "--contrarian", action="store_true",
        help="PTT: 反指標偵測（畢業文 / 歐印文）",
    )
    parser.add_argument(
        "--buzz", action="store_true",
        help="異常熱度偵測：個股討論量 Pump-and-Dump 預警",
    )
    parser.add_argument(
        "--sectors", action="store_true",
        help="PTT: 板塊輪動追蹤",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="執行全部分析",
    )
    parser.add_argument(
        "--influxdb", action="store_true",
        help="將結果寫入 InfluxDB（需先 docker compose up）",
    )
    args = parser.parse_args()

    if args.source == "reddit":
        output = _run_reddit(args)
    else:
        output = _run_ptt(args)

    # 寫入 InfluxDB
    if args.influxdb:
        board_label = args.board if args.source == "ptt" else "reddit"
        store = InfluxStore()
        count = store.write_all(output, board_label)
        store.close()
        print(f"\n已寫入 {count} 筆資料到 InfluxDB。")

    # 輸出
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        _print_output(output)


# ------------------------------------------------------------------
# PTT 分析流程
# ------------------------------------------------------------------

def _run_ptt(args) -> dict:
    if args.update_aliases:
        update_dynamic_aliases()
        print()

    run_contrarian = args.contrarian or args.all
    run_buzz = args.buzz or args.all
    run_sectors = args.sectors or args.all
    run_sentiment = not (args.contrarian or args.buzz or args.sectors) or args.all

    delay = args.delay if args.delay is not None else 0.5
    scraper = PttScraper(board=args.board, delay=delay)
    print(f"正在爬取 PTT {args.board} 版 (共 {args.pages} 頁)...\n")
    posts = scraper.fetch_posts(max_pages=args.pages)

    if not posts:
        print("未抓到任何文章。")
        sys.exit(0)

    output: dict = {}

    if run_sentiment:
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

    if run_contrarian:
        summary = summarize_contrarian(posts)
        output["contrarian"] = {
            "total_posts": summary.total_posts,
            "capitulation_count": summary.capitulation_count,
            "euphoria_count": summary.euphoria_count,
            "capitulation_ratio": round(summary.capitulation_ratio, 4),
            "euphoria_ratio": round(summary.euphoria_ratio, 4),
            "market_signal": summary.market_signal,
            "capitulation_posts": [
                {"title": s.title, "url": s.url, "hits": s.capitulation_hits}
                for s in summary.capitulation_posts
            ],
            "euphoria_posts": [
                {"title": s.title, "url": s.url, "hits": s.euphoria_hits}
                for s in summary.euphoria_posts
            ],
        }

    if run_buzz:
        detector = BuzzDetector()
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
            "anomalies": [
                {"ticker": t.ticker, "name": t.name, "buzz_score": t.buzz_score}
                for t in report.anomalies
            ],
        }

    if run_sectors:
        tracker = SectorTracker()
        sector_report = tracker.analyze(posts)
        output["sectors"] = {
            "total_posts": sector_report.total_posts,
            "ranking": [
                {
                    "sector": h.sector,
                    "mentions": h.mention_count,
                    "keywords": h.matched_keywords,
                    "sample_titles": h.sample_titles,
                }
                for h in sector_report.sectors
            ],
        }

    return output


# ------------------------------------------------------------------
# Reddit 分析流程
# ------------------------------------------------------------------

def _run_reddit(args) -> dict:
    delay = args.delay if args.delay is not None else 1.0
    scraper = RedditScraper(
        subreddits=args.subreddits,
        delay=delay,
        fetch_comments=args.comments,
    )
    subs_str = ", ".join(scraper.subreddits)
    print(f"正在爬取 Reddit [{subs_str}] (每版 {args.limit} 篇)...\n")
    posts = scraper.fetch_posts(limit=args.limit)

    if not posts:
        print("未抓到任何文章。")
        sys.exit(0)

    output: dict = {}

    # 情緒分析
    scorer = RedditSentimentScorer()
    mapper = RedditEntityMapper()
    results = []
    for post in posts:
        sentiment = scorer.analyze_post(post)
        entities = mapper.find_entities(post.title + " " + post.selftext)
        results.append({
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
        })
    output["sentiment"] = results

    return output


# ------------------------------------------------------------------
# 表格輸出
# ------------------------------------------------------------------

def _print_output(output: dict) -> None:
    if "sentiment" in output:
        _print_sentiment_table(output["sentiment"])

    if "contrarian" in output:
        _print_contrarian(output["contrarian"])

    if "buzz" in output:
        _print_buzz(output["buzz"])

    if "sectors" in output:
        _print_sectors(output["sectors"])


def _print_sentiment_table(results: list[dict]) -> None:
    is_reddit = bool(results and "subreddit" in results[0])
    label_map = {"bullish": "🟢Bull", "bearish": "🔴Bear", "neutral": "⚪----"}

    print(f"\n{'='*90}")
    print("  情緒分析 (Sentiment)")
    print(f"{'='*90}")

    if is_reddit:
        print(f"{'Title':<42} {'Signal':>8} {'Score':>6} {'Upvt%':>6} {'Tickers'}")
        print("-" * 90)
        for r in results:
            s = r["sentiment"]
            title = r["title"][:40]
            entities_str = ", ".join(
                f"{e['ticker']}({e['name']})" if e["name"] else e["ticker"]
                for e in r["entities"][:3]
            )
            label = label_map.get(s["label"], s["label"])
            ratio = f"{s['upvote_ratio']:.0%}"
            print(f"{title:<42} {label:>8} {s['score']:>6.1f} {ratio:>6} {entities_str}")
    else:
        print(f"{'標題':<40} {'情緒':>8} {'推':>4} {'噓':>4} {'→':>4} {'相關標的'}")
        print("-" * 90)
        for r in results:
            s = r["sentiment"]
            title = r["title"][:38]
            entities_str = ", ".join(
                f"{e['ticker']}({e['name']})" if e["name"] else e["ticker"]
                for e in r["entities"]
            )
            label = label_map.get(s["label"], s["label"])
            print(
                f"{title:<40} {label:>8} {s['push']:>4} {s['boo']:>4} {s['arrow']:>4} {entities_str}"
            )

    total = len(results)
    bullish = sum(1 for r in results if r["sentiment"]["label"] == "bullish")
    bearish = sum(1 for r in results if r["sentiment"]["label"] == "bearish")
    neutral = total - bullish - bearish
    print("-" * 90)
    print(f"Total: {total} | Bullish: {bullish} | Bearish: {bearish} | Neutral: {neutral}")


def _print_contrarian(data: dict) -> None:
    signal_map = {
        "extreme_fear": "🔴 極度恐慌 (潛在做多訊號)",
        "extreme_greed": "🔴 極度貪婪 (潛在過熱訊號)",
        "fear": "🟡 偏恐慌",
        "greed": "🟡 偏貪婪",
        "neutral": "⚪ 中性",
    }

    print(f"\n{'='*90}")
    print("  反指標偵測 (Contrarian Indicator)")
    print(f"{'='*90}")
    print(f"市場訊號: {signal_map.get(data['market_signal'], data['market_signal'])}")
    print(f"畢業文: {data['capitulation_count']}/{data['total_posts']} "
          f"({data['capitulation_ratio']:.1%})")
    print(f"歐印文: {data['euphoria_count']}/{data['total_posts']} "
          f"({data['euphoria_ratio']:.1%})")

    if data["capitulation_posts"]:
        print("\n畢業文列表:")
        for p in data["capitulation_posts"]:
            print(f"  - {p['title']}")
            print(f"    關鍵字: {', '.join(p['hits'])}")

    if data["euphoria_posts"]:
        print("\n歐印文列表:")
        for p in data["euphoria_posts"]:
            print(f"  - {p['title']}")
            print(f"    關鍵字: {', '.join(p['hits'])}")


def _print_buzz(data: dict) -> None:
    print(f"\n{'='*90}")
    print("  異常熱度偵測 (Buzz Detector)")
    print(f"{'='*90}")

    if data["anomalies"]:
        print("⚠️  異常標的:")
        for a in data["anomalies"]:
            name_str = f" ({a['name']})" if a["name"] else ""
            print(f"  🔥 {a['ticker']}{name_str} — buzz score: {a['buzz_score']}")
        print()

    print(f"{'標的':<16} {'名稱':<12} {'提及':>6} {'Buzz':>8} {'異常':>6}")
    print("-" * 55)
    for t in data["tickers"][:15]:  # 只顯示前 15 名
        name = t["name"][:10] if t["name"] else ""
        flag = "⚠️" if t["anomaly"] else ""
        print(f"{t['ticker']:<16} {name:<12} {t['mentions']:>6} {t['buzz_score']:>8.2f} {flag:>6}")


def _print_sectors(data: dict) -> None:
    print(f"\n{'='*90}")
    print("  板塊輪動 (Sector Rotation)")
    print(f"{'='*90}")

    if not data["ranking"]:
        print("（未偵測到任何板塊關鍵字）")
        return

    for i, s in enumerate(data["ranking"], 1):
        bar = "█" * min(s["mentions"], 40)
        print(f"  {i:>2}. {s['sector']:<12} {bar} ({s['mentions']})")
        if s["keywords"]:
            print(f"      關鍵字: {', '.join(s['keywords'][:5])}")
        if s["sample_titles"]:
            print(f"      範例: {s['sample_titles'][0][:50]}")


if __name__ == "__main__":
    main()
