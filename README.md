# Signals and Sentiment

受 [ICE Reddit Signals and Sentiment](https://www.ice.com/) 啟發的社群情緒分析工具。

同時支援 **PTT (台股)** 與 **Reddit (美股/加密貨幣)** 雙資料源。

### PTT 分析模式
1. **情緒分析** — 推/噓加權計分，判斷看多/看空
2. **反指標偵測** — 「畢業文指數」vs.「歐印文指數」，量化市場恐慌/過熱
3. **異常熱度偵測** — 個股討論量 Z-score，Pump-and-Dump 早期預警
4. **板塊輪動追蹤** — 主題關鍵字熱度排行，捕捉散戶資金關注方向

### Reddit 分析模式
5. **情緒分析** — upvote ratio + 看多/看空關鍵字 (calls/puts, moon/crash...)
6. **實體辨識** — `$TICKER` 語法 + WSB 暱稱 ("su bae" → AMD, "leather jacket man" → NVDA)

## 架構

```
ptt_scraper/                   # PTT 台股分析
├── scraper.py                 # 爬蟲 — www.ptt.cc
├── sentiment.py               # 推/噓/→ 加權計分
├── entity_mapping.py          # 台股暱稱 → 證券代碼
├── feed.py                    # TWSE/TPEX 動態暱稱更新
├── contrarian.py              # 畢業文/歐印文偵測
├── buzz.py                    # 個股異常熱度 Z-score
├── sectors.py                 # 板塊輪動
├── store.py                   # InfluxDB 寫入
└── config.py

reddit_scraper/                # Reddit 美股/加密貨幣分析
├── scraper.py                 # 爬蟲 — Reddit public JSON API
├── sentiment.py               # upvote ratio + keyword 計分
├── entity_mapping.py          # $TICKER + WSB 暱稱辨識
└── config.py

data/
├── aliases.json               # PTT 靜態暱稱表
├── reddit_aliases.json        # Reddit 暱稱表 (美股 + crypto)
└── sectors.json               # 板塊關鍵字定義

main.py                        # CLI 入口 (--source ptt|reddit)
scheduler.py                   # 排程器 (InfluxDB 即時寫入)
docker-compose.yml             # InfluxDB + Grafana
```

## 安裝

```bash
pip install -r requirements.txt
```

需要 Python 3.10+。

## 使用方式

### PTT (台股)

```bash
# 基本情緒分析
python main.py

# 全部分析
python main.py --all --pages 5

# 更新動態暱稱 + 全分析 + JSON
python main.py --update-aliases --all --pages 5 --json
```

### Reddit (美股/加密貨幣)

```bash
# 預設爬 5 個版 (wallstreetbets, stocks, investing, cryptocurrency, bitcoin)
python main.py --source reddit

# 指定 subreddit + 每版抓 50 篇
python main.py --source reddit --subreddits wallstreetbets stocks --limit 50

# 含留言分析（較慢但更準確）+ JSON 輸出
python main.py --source reddit --comments --json
```

### CLI 參數

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `--source` | `ptt` | 資料源: `ptt` 或 `reddit` |
| `--board` | `Stock` | PTT 看板 |
| `--pages` | `1` | PTT 往前爬幾頁 |
| `--subreddits` | 5 個版 | Reddit subreddit 列表 |
| `--limit` | `25` | Reddit 每版抓幾篇 (上限 100) |
| `--comments` | off | Reddit: 進入文章抓留言 |
| `--delay` | auto | 請求間隔 (PTT 0.5s, Reddit 1.0s) |
| `--json` | off | JSON 格式輸出 |
| `--update-aliases` | off | PTT: 更新動態暱稱 |
| `--contrarian` | off | PTT: 反指標偵測 |
| `--buzz` | off | 異常熱度偵測 |
| `--sectors` | off | PTT: 板塊輪動追蹤 |
| `--all` | off | 執行全部分析 |

> 單獨指定 `--contrarian`、`--buzz`、`--sectors` 時只跑該分析。
> 不帶任何分析 flag 則預設跑情緒分析。`--all` 全部一起跑。

---

## 分析模式詳解

### 1a. PTT 情緒分析

基於推文標籤的加權分數：

| 標籤 | 意義 | 權重 |
|------|------|------|
| 推 | 看多 / 正面 | +1.0 |
| 噓 | 看空 / 負面 | -1.5 |
| → | 中性補充 | 0.0 |

- `score >= 2.0` → bullish（看多）
- `score <= -2.0` → bearish（看空）
- 其餘 → neutral（中性）

> 噓的權重較高（-1.5）是因為在股板中，噓通常代表更強烈的負面態度。

### 2. 反指標偵測 (Contrarian Indicator)

偵測兩類極端情緒文章：

**畢業文（Capitulation）** — 散戶投降訊號：
> 畢業、賠光、認賠、斷頭、融資追繳、違約交割、砍在阿呆谷...

**歐印文（Euphoria）** — 散戶過度樂觀訊號：
> 歐印、All in、梭哈、睏霸數錢、財富自由、上車、衝了...

市場訊號判定：
- 畢業文佔比 >= 15% → `extreme_fear`（潛在做多訊號）
- 歐印文佔比 >= 15% → `extreme_greed`（潛在過熱訊號）

### 3. 異常熱度偵測 (Buzz Detector)

計算每支股票的討論量 Z-score（相對歷史基線的標準差倍數）。

適用場景：冷門小型股突然出現大量討論但成交量尚未放大 → Pump-and-Dump 早期訊號。

- 每次執行自動存入 `data/buzz_history.json` 作為歷史基線
- `buzz_score >= 2.0` 標記為異常

### 4. 板塊輪動 (Sector Rotation)

從文章中統計主題關鍵字頻率，追蹤散戶資金關注方向的變化。

內建板塊定義（`data/sectors.json`）：
AI伺服器、散熱、CPO光通訊、半導體、航運、金融、電動車、機器人、營建資產、生技醫療

輸出範例：
```
   1. 半導體      ████████████ (12)
      關鍵字: 台積, 晶圓, 先進封裝
   2. AI伺服器    ████████ (8)
      關鍵字: ai伺服器, gpu, 算力
   3. 散熱        ███ (3)
      關鍵字: 散熱, 液冷
```

---

## 實體辨識 (Entity Mapping)

暱稱對應分為兩層：

| 層級 | 檔案 | 說明 |
|------|------|------|
| 靜態 | `data/aliases.json` | 手動維護，版本控制 |
| 動態 | `data/dynamic_aliases.json` | 由 `--update-aliases` 自動產生 |

動態暱稱自動從 TWSE/TPEX 公開 API 取得：
- **股王** — 全市場收盤價最高的股票
- **股后** — 全市場收盤價第二高的股票

常見靜態對應：

| 暱稱 | 代碼 | 公司 |
|------|------|------|
| GG、神山、護國神山、台GG | 2330 | 台積電 |
| 郭董、土城鵝、海公公 | 2317 | 鴻海 |
| 發哥、MTK | 2454 | 聯發科 |
| 大盤、加權 | TAIEX | 加權指數 |
| ... | ... | ... |

完整對應表見 [`data/aliases.json`](data/aliases.json)。也支援直接辨識純數字代碼（如 `2330`、`2330.TW`）。

## 即時監控 (Live Stack)

將靜態 JSON 轉為即時時間序列數據流，用 Grafana 視覺化。

### 架構

```
[Python 爬蟲] → [InfluxDB 2.x] → [Grafana Dashboard]
     ↑                                    ↓
  scheduler.py (每 N 分鐘)          瀏覽器 localhost:3000
```

### Quick Start

```bash
# 1. 啟動 InfluxDB + Grafana
docker compose up -d

# 2. 單次寫入測試
pip install -r requirements.txt
python main.py --all --influxdb

# 3. 開啟 Grafana
#    http://localhost:3000 (admin / admin)
#    Dashboard 已自動建好: "PTT Signals & Sentiment"

# 4. 啟動排程器（每 5 分鐘自動爬取 + 寫入）
python scheduler.py --interval 5 --pages 2
```

### Grafana Dashboard 內建面板

| 面板 | 類型 | 說明 |
|------|------|------|
| 看板情緒分數 | Time Series | 平均 sentiment score 趨勢線，紅/黃/綠區間 |
| 恐慌/貪婪指數 | Gauge | 畢業文 vs. 歐印文比例的即時儀表 |
| 反指標趨勢 | Time Series | 畢業文/歐印文比例隨時間變化 |
| 個股討論熱度 Top 10 | Bar Chart | 討論量最高的前 10 支股票 |
| Buzz 異常標的 | Table | Z-score >= 2.0 的異常飆升股票 |
| 板塊輪動 | Bar Chart | 各主題熱度排行 |
| 看多/看空文章數 | Stacked Bar | 每輪的 bullish/bearish/neutral 堆疊圖 |
| 板塊熱度趨勢 | Time Series | 各板塊討論量的時間變化（觀察輪動轉折） |

### 排程器參數

```bash
python scheduler.py --help

  --board      目標看板 (預設: Stock)
  --pages      每輪爬幾頁 (預設: 1)
  --delay      HTTP 請求間隔 (預設: 0.5s)
  --interval   排程間隔分鐘數 (預設: 5)
```

### 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `INFLUXDB_URL` | `http://localhost:8086` | InfluxDB 連線 URL |
| `INFLUXDB_TOKEN` | `ptt-dev-token` | API Token |
| `INFLUXDB_ORG` | `ptt-lab` | Organization |
| `INFLUXDB_BUCKET` | `ptt_sentiment` | Bucket 名稱 |

> 正式環境請務必更換 Token 和密碼。docker-compose.yml 中的預設值僅供開發用。

---

## 作為模組使用

```python
from ptt_scraper import (
    PttScraper, SentimentScorer, EntityMapper,
    summarize_contrarian, BuzzDetector, SectorTracker,
)

scraper = PttScraper(board="Stock")
posts = scraper.fetch_posts(max_pages=5)

# 情緒分析
scorer = SentimentScorer()
for post in posts:
    result = scorer.analyze_post(post)
    print(f"{post.title} → {result.label} (score={result.score})")

# 反指標
summary = summarize_contrarian(posts)
print(f"市場訊號: {summary.market_signal}")
print(f"畢業文: {summary.capitulation_count}, 歐印文: {summary.euphoria_count}")

# 異常熱度
detector = BuzzDetector()
report = detector.analyze(posts)
for t in report.anomalies:
    print(f"⚠️ {t.ticker} ({t.name}) buzz={t.buzz_score}")

# 板塊輪動
tracker = SectorTracker()
sector_report = tracker.analyze(posts)
for h in sector_report.sectors:
    print(f"{h.sector}: {h.mention_count} mentions")
```

## License

MIT
