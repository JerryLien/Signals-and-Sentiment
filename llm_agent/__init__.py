"""LLM Agent — 異常事件自動歸因 (The "Why" Layer)。

當情緒異常觸發時 (Z-score > 3 / Premium 突破 ±0.5)，
自動從 InfluxDB 撈出高權重貼文，交由 LLM 摘要原因，
結果寫入 Grafana Annotation 標註在時間軸上。
"""

from llm_agent.config import LLMConfig
from llm_agent.explainer import AnomalyExplainer
from llm_agent.annotator import GrafanaAnnotator
from llm_agent.monitor import AnomalyMonitor

__all__ = ["LLMConfig", "AnomalyExplainer", "GrafanaAnnotator", "AnomalyMonitor"]
