# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Community sentiment analysis platform analyzing market sentiment from **PTT (Taiwan Stock Board)** and **Reddit (US stocks/crypto)**. Inspired by ICE's Reddit Signals and Sentiment. Dual-source analysis with cross-market ticker mapping (e.g., PTT 2330 ↔ Reddit TSM for TSMC).

**Stack**: Python 3.10+, InfluxDB 2.x (time-series storage), Grafana 11.0.0 (dashboards), Docker Compose, BeautifulSoup (PTT scraping), PRAW (Reddit API).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# CLI - PTT analysis
python main.py                                    # Basic sentiment
python main.py --all --pages 5 --json             # Full analysis, JSON output
python main.py --update-aliases --all --pages 5   # Refresh dynamic aliases first
python main.py --contrarian                       # Graduation/euphoria detection
python main.py --buzz                             # Z-score anomaly detection
python main.py --sectors                          # Sector rotation tracking

# CLI - Reddit analysis
python main.py --source reddit                    # Default 7 subreddits
python main.py --source reddit --comments --json  # Include comments

# Docker (full stack: scraper + InfluxDB + Grafana)
cp .env.example .env   # Fill in secrets first
docker compose up -d
# Grafana: http://localhost:3000  InfluxDB: http://localhost:8086

# Scheduler (live monitoring)
python scheduler.py --source both --interval 5 --pages 2

# LLM Agent (anomaly auto-explanation)
python -m llm_agent.monitor          # Continuous polling
python -m llm_agent.monitor --once   # Single detection run (testing)
```

## Testing & Linting

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests with coverage (minimum 60% required)
pytest tests/ -v --tb=short

# Run a single test file
pytest tests/test_buzz.py -v

# Run a single test
pytest tests/test_buzz.py::TestBuzzDetector::test_detect_anomaly -v

# Formatting & linting
black --check --line-length 100 ptt_scraper/ reddit_scraper/ tests/ main.py scheduler.py
flake8 ptt_scraper/ reddit_scraper/ tests/ main.py scheduler.py
pylint ptt_scraper/ reddit_scraper/ --fail-under=7.0
mypy ptt_scraper/ reddit_scraper/ --ignore-missing-imports --disable-error-code=import-untyped
```

Config: `pyproject.toml` (black, flake8, pylint, mypy, pytest). Line length: 100. Pre-commit hooks configured in `.pre-commit-config.yaml`. CI runs lint + typecheck + test + docker-build on push/PR to main.

## Architecture

```
main.py          CLI entry point, orchestrates all analysis modes
scheduler.py     Periodic scraping loop with InfluxDB writes, signal handling

ptt_scraper/     Taiwan stock analysis module
  scraper.py     Web scraper for www.ptt.cc (BeautifulSoup + over18 cookie)
  sentiment.py   Push/boo weighted scoring (push×1.0, boo×-1.5)
  entity_mapping.py  Stock nickname → ticker (static aliases + dynamic TWSE/TPEX)
  contrarian.py  Graduation text / euphoria keyword detection
  buzz.py        Anomaly detection via Z-score on mention frequency
  sectors.py     Sector rotation tracking by keyword frequency
  feed.py        Dynamic alias updating from TWSE/TPEX APIs
  store.py       InfluxDB time-series writer (batched Points API)
  config.py      Constants & weights

reddit_scraper/  US stock/crypto analysis module
  scraper.py     Dual backend: PRAW (OAuth2, preferred) → JSON API fallback
  sentiment.py   Upvote ratio + keyword-based scoring
  entity_mapping.py  $TICKER extraction + WSB slang mapping
  config.py      Constants & default subreddits

data/            Configuration & mapping files
  aliases.json         Static PTT nickname → ticker mappings
  reddit_aliases.json  Reddit ticker & slang mappings
  sectors.json         10 sector definitions with keywords
  global_mapping.json  Cross-market ticker pairs (PTT ↔ Reddit)
  dynamic_aliases.json Auto-generated from TWSE/TPEX (gitignored)
  buzz_history.json    Historical mention baselines (gitignored)

llm_agent/       LLM-powered anomaly explanation ("The Why Layer")
  monitor.py     Polls InfluxDB for anomalies, triggers LLM + Grafana annotation
  explainer.py   Queries top posts from InfluxDB, calls LLM for summary
  annotator.py   Writes explanations to Grafana via annotation API
  config.py      LLM provider, thresholds, polling config (all from env vars)

grafana/         Dashboard & provisioning configs
  dashboards/ptt-signals.json   Main dashboard (12 panels, auto-provisioned)
  provisioning/                 Datasource, alerting, dashboard configs

tests/           pytest test suite (83+ tests, 60% coverage minimum)
```

## Key Design Decisions

- **Sentiment weights are asymmetric**: PTT boo weight (-1.5) > push weight (1.0) because negative sentiment is stronger in Taiwan stock forums. Reddit uses upvote_ratio centered at 0.5.
- **Entity mapping priority**: Longer aliases match first to avoid false positives. Three layers: static JSON → dynamic TWSE/TPEX API → regex digit codes.
- **Reddit dual-backend**: PRAW (600 req/min with OAuth2) is preferred; public JSON API (60 req/min) is automatic fallback when PRAW credentials are absent.
- **Rate limiting**: 0.5s delay for PTT, 1.0s for Reddit. Configurable via `--delay`.
- **Contrarian thresholds**: graduation ≥ 15% → extreme_fear signal; euphoria ≥ 15% → extreme_greed signal.
- **Buzz detection**: Z-score ≥ 2.0 flags anomaly; 30-period rolling window persisted to `data/buzz_history.json`.
- **Timezone**: Fixed to UTC+8 (Taiwan) for all timestamp parsing.
- **LLM Agent**: Polls InfluxDB for two anomaly types — buzz Z-score > 3.0 and sentiment premium ±0.5 (TSM vs 2330). Uses Anthropic (Claude) or OpenAI as backend. Generates a 30-char Chinese summary written as a Grafana annotation. Dedup cooldown prevents duplicate triggers (default 1 hour).

## Environment Variables

Secrets live in `.env` (never committed). See `.env.example` for template. Key vars:
- `INFLUXDB_TOKEN`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET` — InfluxDB connection
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` — Reddit OAuth2 (optional, enables PRAW)
- `INFLUXDB_RETENTION_DAYS` — Data retention (default 90)
- `LLM_PROVIDER` — `anthropic` (default) or `openai`
- `LLM_API_KEY` — API key for the chosen LLM provider
- `LLM_MODEL` — Model name (default: `claude-sonnet-4-5-20250929` / `gpt-4o-mini`)
- `GRAFANA_API_KEY` — Grafana annotation API key (falls back to basic auth)

## Grafana Alerts

Two pre-configured alert rules in `grafana/provisioning/alerting/alerts.yml`:
1. **Buzz Z-score > 3.0** — Potential pump-and-dump warning
2. **Euphoria ≥ 15%** — Market overheating signal
