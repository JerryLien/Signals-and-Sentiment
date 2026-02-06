#!/usr/bin/env python3
"""PTT 股板情緒分析 — 受 ICE Reddit Signals and Sentiment 啟發。

用法:
    python main.py                              # 基本情緒分析
    python main.py --pages 3 --json             # 多頁 + JSON 輸出
    python main.py --update-aliases             # 先更新動態暱稱再分析
    python main.py --contrarian                 # 反指標偵測 (畢業文/歐印)
    python main.py --buzz                       # 異常熱度偵測 (Pump-and-Dump 預警)
    python main.py --sectors                    # 板塊輪動追蹤
    python main.py --all                        # 全部分析一次跑完
"""

import argparse
import json
import sys

from ptt_scraper import (
    BuzzDetector,
    EntityMapper,
    PttScraper,
    SectorTracker,
    SentimentScorer,
    summarize_contrarian,
    update_dynamic_aliases,
)


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
    parser.add_argument(
        "--update-aliases", action="store_true",
        help="從 TWSE/TPEX 更新動態暱稱（股王、股后等）",
    )
    parser.add_argument(
        "--contrarian", action="store_true",
        help="反指標偵測：畢業文指數 / 歐印指數",
    )
    parser.add_argument(
        "--buzz", action="store_true",
        help="異常熱度偵測：個股討論量 Pump-and-Dump 預警",
    )
    parser.add_argument(
        "--sectors", action="store_true",
        help="板塊輪動追蹤：主題熱度排行",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="執行全部分析（sentiment + contrarian + buzz + sectors）",
    )
    args = parser.parse_args()

    if args.update_aliases:
        update_dynamic_aliases()
        print()

    # 決定啟用哪些分析
    run_contrarian = args.contrarian or args.all
    run_buzz = args.buzz or args.all
    run_sectors = args.sectors or args.all
    run_sentiment = not (args.contrarian or args.buzz or args.sectors) or args.all

    # 爬取
    scraper = PttScraper(board=args.board, delay=args.delay)
    print(f"正在爬取 PTT {args.board} 版 (共 {args.pages} 頁)...\n")
    posts = scraper.fetch_posts(max_pages=args.pages)

    if not posts:
        print("未抓到任何文章。")
        sys.exit(0)

    output: dict = {}

    # 1. 基本情緒分析
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

    # 2. 反指標偵測
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

    # 3. 異常熱度偵測
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

    # 4. 板塊輪動
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

    # 輸出
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        _print_output(output)


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
    print(f"\n{'='*90}")
    print("  情緒分析 (Sentiment)")
    print(f"{'='*90}")
    print(f"{'標題':<40} {'情緒':>8} {'推':>4} {'噓':>4} {'→':>4} {'相關標的'}")
    print("-" * 90)
    for r in results:
        s = r["sentiment"]
        title = r["title"][:38]
        entities_str = ", ".join(
            f"{e['ticker']}({e['name']})" if e["name"] else e["ticker"]
            for e in r["entities"]
        )
        label_map = {
            "bullish": "🟢看多",
            "bearish": "🔴看空",
            "neutral": "⚪中性",
        }
        label = label_map.get(s["label"], s["label"])
        print(
            f"{title:<40} {label:>8} {s['push']:>4} {s['boo']:>4} {s['arrow']:>4} {entities_str}"
        )

    total = len(results)
    bullish = sum(1 for r in results if r["sentiment"]["label"] == "bullish")
    bearish = sum(1 for r in results if r["sentiment"]["label"] == "bearish")
    neutral = total - bullish - bearish
    print("-" * 90)
    print(f"共 {total} 篇 | 看多: {bullish} | 看空: {bearish} | 中性: {neutral}")


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
