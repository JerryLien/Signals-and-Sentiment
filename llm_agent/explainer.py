"""AnomalyExplainer — 從 InfluxDB 撈出高權重貼文，交由 LLM 解釋異常原因。

觸發時機：Z-score > 3 或 Sentiment Premium 突破 ±0.5。
輸出：一句 30 字以內的繁體中文摘要（寫入 Grafana Annotation）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from influxdb_client import InfluxDBClient

from llm_agent.config import LLMConfig

logger = logging.getLogger(__name__)

# ── System Prompt: 單一來源異常 (buzz_zscore) ────────────────
SYSTEM_PROMPT_SINGLE = """\
你是避險基金的資深交易員，專精社群情緒驅動的事件交易。
你的任務是閱讀 Reddit 或 PTT 的熱門貼文，判斷情緒暴衝的真正原因。

分析規則：
1. 區分三種貼文類型：
   - 「事件驅動」：財報、法說會、分析師升降評、政策消息、技術突破 → 重點報告。
   - 「YOLO 無腦跟單」：大量跟風但無具體觸發事件 → 回答「情緒過熱，無基本面催化」。
   - 「反串 (Sarcasm)」：WSB 風格的自嘲、反話 ("so trash I'm buying calls") → 忽略不計。
2. 忽略 "To the moon", "HODL", "上看", "歐印" 等口號。
3. 輸出限制在 30 個字以內 (繁體中文)。
4. 不要加引號或標點符號前綴。直接輸出摘要。"""

# ── System Prompt: 跨市場異常 (premium_breakout) ─────────────
SYSTEM_PROMPT_CROSS = """\
你是避險基金的跨市場套利交易員，負責解讀台股 (PTT) 與美股 (Reddit) 的情緒分歧。
你會收到兩組貼文：Reddit (美股散戶) 和 PTT (台股散戶)。

分析規則：
1. 判斷雙邊是「共振」還是「對作」：
   - 共振：兩邊都在嗨 (同方向情緒) → 報告觸發共振的共同事件。
   - 對作：一邊看多一邊倒貨 (情緒分歧) → 報告分歧原因，指出哪一邊可能錯。
2. 區分貼文類型：
   - 「事件驅動」→ 重點報告。
   - 「YOLO 無腦跟單」→ 標記「情緒過熱，無基本面催化」。
   - 「反串 (Sarcasm)」→ 忽略不計。
3. 輸出格式（繁體中文，50 字以內）：
   [共振/對作] 一句話原因
4. 不要加引號或標點符號前綴。直接輸出。"""


@dataclass
class AnomalyEvent:
    """一筆異常事件的描述。"""
    event_type: str          # "buzz_zscore" | "premium_breakout"
    ticker: str              # e.g. "TSM", "2330"
    source: str              # "ptt" | "reddit" | "cross"
    value: float             # Z-score 或 premium 值
    titles: list[str]        # 相關高權重貼文標題


@dataclass
class Explanation:
    """LLM 生成的解釋。"""
    event: AnomalyEvent
    summary: str             # LLM 輸出的一句話摘要
    model: str               # 使用的 LLM 模型


class AnomalyExplainer:
    """異常事件歸因引擎。

    1. query_top_posts()  → 從 InfluxDB 撈高權重貼文標題
    2. explain()          → 呼叫 LLM 產生摘要
    """

    def __init__(self, config: LLMConfig | None = None):
        self.cfg = config or LLMConfig()
        self._influx = InfluxDBClient(
            url=self.cfg.INFLUXDB_URL,
            token=self.cfg.INFLUXDB_TOKEN,
            org=self.cfg.INFLUXDB_ORG,
        )
        self._query_api = self._influx.query_api()

    def close(self) -> None:
        self._influx.close()

    # ── Step 1: 撈出相關貼文 ───────────────────────────────

    def query_top_posts(
        self,
        ticker: str,
        source: str = "",
        minutes: int = 30,
        limit: int = 10,
    ) -> list[str]:
        """從 InfluxDB 查詢最近 N 分鐘內，該 ticker 權重最高的貼文標題。"""
        source_filter = ""
        if source and source != "cross":
            source_filter = f'|> filter(fn: (r) => r.source == "{source}")'

        flux = f"""
from(bucket: "{self.cfg.INFLUXDB_BUCKET}")
  |> range(start: -{minutes}m)
  |> filter(fn: (r) => r._measurement == "post_sentiment")
  |> filter(fn: (r) => r.ticker == "{ticker}")
  {source_filter}
  |> filter(fn: (r) => r._field == "title")
  |> last()
  |> group()
  |> limit(n: {limit})
"""
        titles: list[str] = []
        try:
            tables = self._query_api.query(flux)
            for table in tables:
                for record in table.records:
                    val = record.get_value()
                    if val:
                        titles.append(str(val))
        except Exception as exc:
            logger.warning("InfluxDB query failed: %s", exc)

        return titles

    # ── Step 2: 呼叫 LLM ──────────────────────────────────

    def explain(self, event: AnomalyEvent) -> Explanation:
        """呼叫 LLM 解釋異常事件。

        自動根據 LLM_PROVIDER 選擇 Anthropic 或 OpenAI。
        """
        titles = event.titles
        if not titles:
            titles = self.query_top_posts(
                ticker=event.ticker,
                source=event.source,
                minutes=30,
            )

        if not titles:
            return Explanation(
                event=event,
                summary="無法取得相關貼文，無法判斷原因",
                model="fallback",
            )

        # 選擇 system prompt + 組裝 user prompt
        is_cross = event.event_type == "premium_breakout"
        system_prompt = SYSTEM_PROMPT_CROSS if is_cross else SYSTEM_PROMPT_SINGLE

        if is_cross:
            # 跨市場事件：分開呈現 Reddit 和 PTT 標題
            reddit_titles = [t for t in titles if t.startswith("[Reddit]")]
            ptt_titles = [t for t in titles if t.startswith("[PTT]")]
            # 如果沒有前綴標記，按前後順序分（前半 Reddit, 後半 PTT）
            if not reddit_titles and not ptt_titles:
                mid = len(titles) // 2
                reddit_titles = titles[:mid]
                ptt_titles = titles[mid:]

            premium_dir = "Reddit 偏多 (外資看漲)" if event.value > 0 else "PTT 偏多 (內資過熱)"
            user_prompt = (
                f"跨市場標的：TSM (Reddit) / 2330 (PTT)\n"
                f"情緒溢價：{event.value:+.2f} → {premium_dir}\n\n"
                f"Reddit 美股散戶 (r/wallstreetbets 等)：\n"
                + "\n".join(f"- {t}" for t in reddit_titles[:5])
                + f"\n\nPTT 台股散戶 (Stock 版)：\n"
                + "\n".join(f"- {t}" for t in ptt_titles[:5])
            )
        else:
            event_desc = f"Z-score = {event.value:.1f} (討論量暴增)"
            user_prompt = (
                f"股票代碼：{event.ticker}\n"
                f"異常類型：{event_desc}\n"
                f"來源：{event.source}\n"
                f"熱門貼文標題列表：\n"
                + "\n".join(f"- {t}" for t in titles[:10])
            )

        provider = self.cfg.LLM_PROVIDER.lower()
        if provider == "anthropic":
            summary = self._call_anthropic(user_prompt, system_prompt)
        elif provider == "openai":
            summary = self._call_openai(user_prompt, system_prompt)
        else:
            logger.error("Unknown LLM_PROVIDER: %s", provider)
            summary = f"[{event.ticker}] 情緒異常但 LLM 未設定"

        return Explanation(
            event=event,
            summary=summary,
            model=self.cfg.LLM_MODEL,
        )

    # ── LLM Backends ──────────────────────────────────────

    def _call_anthropic(self, user_prompt: str, system_prompt: str) -> str:
        """透過 Anthropic SDK 呼叫 Claude。"""
        try:
            import anthropic
        except ImportError:
            logger.error("anthropic package not installed")
            return "LLM 呼叫失敗: anthropic 未安裝"

        try:
            client = anthropic.Anthropic(api_key=self.cfg.LLM_API_KEY)
            message = client.messages.create(
                model=self.cfg.LLM_MODEL,
                max_tokens=150,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text.strip()
        except Exception as exc:
            logger.error("Anthropic API error: %s", exc)
            return f"LLM 呼叫失敗: {exc}"

    def _call_openai(self, user_prompt: str, system_prompt: str) -> str:
        """透過 OpenAI SDK 呼叫 GPT。"""
        try:
            import openai
        except ImportError:
            logger.error("openai package not installed")
            return "LLM 呼叫失敗: openai 未安裝"

        try:
            client = openai.OpenAI(api_key=self.cfg.LLM_API_KEY)
            response = client.chat.completions.create(
                model=self.cfg.LLM_MODEL,
                max_tokens=150,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("OpenAI API error: %s", exc)
            return f"LLM 呼叫失敗: {exc}"
