# PTT Signals and Sentiment

受 [ICE Reddit Signals and Sentiment](https://www.ice.com/) 啟發的 PTT 股板情緒分析工具。

從 PTT 網頁版 (www.ptt.cc) 爬取文章與推文，透過推/噓加權計分產生情緒指標，並自動辨識文中提及的台股標的。

## 架構

```
ptt_scraper/
├── scraper.py          # 爬蟲核心 — 抓取文章列表、內文、推文
├── sentiment.py        # 情緒分析 — 推/噓/→ 加權計分
├── entity_mapping.py   # 實體辨識 — PTT 暱稱 → 證券代碼
└── config.py           # 設定常數 (URL、Headers、權重)
main.py                 # CLI 入口
```

## 安裝

```bash
pip install -r requirements.txt
```

需要 Python 3.10+。

## 使用方式

```bash
# 預設爬 Stock 版最新 1 頁
python main.py

# 爬 3 頁，以 JSON 輸出
python main.py --pages 3 --json

# 指定看板與請求間隔
python main.py --board Gossiping --pages 2 --delay 1.0
```

### CLI 參數

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `--board` | `Stock` | 目標看板 |
| `--pages` | `1` | 往前爬幾頁 |
| `--delay` | `0.5` | 每次請求間隔秒數 |
| `--json` | off | 以 JSON 格式輸出 |

### 輸出範例

**表格模式（預設）：**

```
標題                                     情緒      推   噓   →  相關標的
------------------------------------------------------------------------------------------
[請益] GG還能追嗎                         🟢看多   12    1    5  2330(台積電)
[閒聊] 航運三雄今天怎麼了                  🔴看空    3    8    4  2603(長榮), 2609(陽明), 2615(萬海)
------------------------------------------------------------------------------------------
共 2 篇 | 看多: 1 | 看空: 1 | 中性: 0
```

**JSON 模式 (`--json`)：**

```json
[
  {
    "title": "[請益] GG還能追嗎",
    "url": "https://www.ptt.cc/bbs/Stock/M.1234567890.A.123.html",
    "author": "stock_man",
    "date": "Wed Feb  5 10:30:00 2026",
    "sentiment": {
      "score": 10.5,
      "label": "bullish",
      "push": 12,
      "boo": 1,
      "arrow": 5
    },
    "entities": [
      { "ticker": "2330", "name": "台積電", "matched": "gg" }
    ]
  }
]
```

## 情緒計分方式

基於推文標籤的加權分數：

| 標籤 | 意義 | 權重 |
|------|------|------|
| 推 | 看多 / 正面 | +1.0 |
| 噓 | 看空 / 負面 | -1.5 |
| → | 中性補充 | 0.0 |

**分類規則：**
- `score >= 2.0` → bullish（看多）
- `score <= -2.0` → bearish（看空）
- 其餘 → neutral（中性）

> 噓的權重較高（-1.5）是因為在股板中，噓通常代表更強烈的負面態度。

## 實體辨識 (Entity Mapping)

類似 ICE 將 Reddit 上的 "Micky Mouse" 對應到 Disney ticker，本工具將 PTT 鄉民慣用的暱稱對應到台股證券代碼：

| 暱稱 | 代碼 | 公司 |
|------|------|------|
| GG、神山、護國神山、台GG | 2330 | 台積電 |
| 郭董、土城鵝、海公公 | 2317 | 鴻海 |
| 發哥、MTK | 2454 | 聯發科 |
| 大盤、加權 | TAIEX | 加權指數 |
| ... | ... | ... |

完整對應表見 [`entity_mapping.py`](ptt_scraper/entity_mapping.py)。也支援直接辨識純數字代碼（如 `2330`、`2330.TW`）。

可透過 `EntityMapper(extra_aliases={...})` 擴充自訂暱稱。

## 作為模組使用

```python
from ptt_scraper import PttScraper, SentimentScorer, EntityMapper

scraper = PttScraper(board="Stock")
posts = scraper.fetch_posts(max_pages=2)

scorer = SentimentScorer()
mapper = EntityMapper()

for post in posts:
    result = scorer.analyze_post(post)
    entities = mapper.find_entities(post.title + " " + post.content)
    print(f"{post.title} → {result.label} (score={result.score})")
    print(f"  提及: {[e['ticker'] for e in entities]}")
```

## License

MIT
