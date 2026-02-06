"""LLM Agent 設定 — 所有閾值與連線參數集中管理。"""

import os


class LLMConfig:
    """從環境變數讀取所有 LLM Agent 設定。"""

    # ── LLM Provider ────────────────────────────────────
    # 支援 "anthropic" / "openai"，由環境變數決定
    LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "anthropic")
    LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "")
    LLM_MODEL: str = os.environ.get(
        "LLM_MODEL",
        "claude-sonnet-4-5-20250929" if LLM_PROVIDER == "anthropic" else "gpt-4o-mini",
    )

    # ── Anomaly Thresholds ──────────────────────────────
    BUZZ_ZSCORE_THRESHOLD: float = float(
        os.environ.get("LLM_BUZZ_ZSCORE_THRESHOLD", "3.0"),
    )
    PREMIUM_THRESHOLD: float = float(
        os.environ.get("LLM_PREMIUM_THRESHOLD", "0.5"),
    )

    # ── InfluxDB (與主系統共用) ──────────────────────────
    INFLUXDB_URL: str = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
    INFLUXDB_TOKEN: str = os.environ.get("INFLUXDB_TOKEN", "ptt-dev-token")
    INFLUXDB_ORG: str = os.environ.get("INFLUXDB_ORG", "ptt-lab")
    INFLUXDB_BUCKET: str = os.environ.get("INFLUXDB_BUCKET", "ptt_sentiment")

    # ── Grafana Annotation API ──────────────────────────
    GRAFANA_URL: str = os.environ.get("GRAFANA_URL", "http://localhost:3000")
    GRAFANA_API_KEY: str = os.environ.get("GRAFANA_API_KEY", "")
    # 若無 API Key，用 basic auth (admin:password)
    GRAFANA_USER: str = os.environ.get("GRAFANA_USER", "admin")
    GRAFANA_PASSWORD: str = os.environ.get(
        "GRAFANA_PASSWORD",
        os.environ.get("GF_SECURITY_ADMIN_PASSWORD", "admin"),
    )

    # ── Monitor ─────────────────────────────────────────
    # 檢查間隔 (秒)
    POLL_INTERVAL: int = int(os.environ.get("LLM_POLL_INTERVAL", "300"))
    # 回顧窗口 (分鐘) — 每次查詢過去 N 分鐘的異常
    LOOKBACK_MINUTES: int = int(os.environ.get("LLM_LOOKBACK_MINUTES", "10"))
    # 去重冷卻 (秒) — 同一 ticker 在 N 秒內不重複觸發
    DEDUP_COOLDOWN: int = int(os.environ.get("LLM_DEDUP_COOLDOWN", "3600"))
