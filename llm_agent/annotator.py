"""GrafanaAnnotator — 將 LLM 解釋寫入 Grafana Annotation。

在 Grafana 時間軸上標註文字，讓使用者一眼看到「為什麼」。
使用 Grafana HTTP API: POST /api/annotations
"""

from __future__ import annotations

import logging
import time

import requests

from llm_agent.config import LLMConfig
from llm_agent.explainer import Explanation

logger = logging.getLogger(__name__)

# Annotation tag 前綴，方便在 Grafana 過濾
TAG_PREFIX = "llm-agent"


class GrafanaAnnotator:
    """透過 Grafana HTTP API 建立 Annotation。"""

    def __init__(self, config: LLMConfig | None = None):
        self.cfg = config or LLMConfig()
        self._base_url = self.cfg.GRAFANA_URL.rstrip("/")

    def _headers(self) -> dict[str, str]:
        """建立 HTTP headers — 優先使用 API Key，否則 basic auth。"""
        headers = {"Content-Type": "application/json"}
        if self.cfg.GRAFANA_API_KEY:
            headers["Authorization"] = f"Bearer {self.cfg.GRAFANA_API_KEY}"
        return headers

    def _auth(self) -> tuple[str, str] | None:
        """若無 API Key，回傳 basic auth tuple。"""
        if self.cfg.GRAFANA_API_KEY:
            return None
        return (self.cfg.GRAFANA_USER, self.cfg.GRAFANA_PASSWORD)

    def annotate(self, explanation: Explanation) -> bool:
        """將一筆 Explanation 寫入 Grafana Annotation。

        Returns
        -------
        bool
            是否成功寫入。
        """
        event = explanation.event

        # 組裝 annotation 文字
        type_label = {
            "buzz_zscore": "Buzz Z-score 異常",
            "premium_breakout": "情緒溢價突破",
        }.get(event.event_type, event.event_type)

        text = (
            f"<b>{type_label}</b> [{event.ticker}] "
            f"(value={event.value:+.2f}, source={event.source})<br>"
            f"{explanation.summary}<br>"
            f"<i>— {explanation.model}</i>"
        )

        tags = [
            TAG_PREFIX,
            event.event_type,
            event.ticker,
            event.source,
        ]

        payload = {
            "text": text,
            "tags": tags,
            "time": int(time.time() * 1000),  # epoch ms
        }

        url = f"{self._base_url}/api/annotations"
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                auth=self._auth(),
                timeout=10,
            )
            if resp.status_code in (200, 201):
                ann_id = resp.json().get("id", "?")
                logger.info(
                    "Annotation created: id=%s ticker=%s summary=%s",
                    ann_id,
                    event.ticker,
                    explanation.summary,
                )
                return True
            else:
                logger.warning(
                    "Grafana annotation failed: %d %s",
                    resp.status_code,
                    resp.text,
                )
                return False
        except Exception as exc:
            logger.error("Grafana annotation error: %s", exc)
            return False
