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
```

No test suite exists in this project.

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

grafana/         Dashboard & provisioning configs
  dashboards/ptt-signals.json   Main dashboard (12 panels, auto-provisioned)
  provisioning/                 Datasource, alerting, dashboard configs
```

## Key Design Decisions

- **Sentiment weights are asymmetric**: PTT boo weight (-1.5) > push weight (1.0) because negative sentiment is stronger in Taiwan stock forums. Reddit uses upvote_ratio centered at 0.5.
- **Entity mapping priority**: Longer aliases match first to avoid false positives. Three layers: static JSON → dynamic TWSE/TPEX API → regex digit codes.
- **Reddit dual-backend**: PRAW (600 req/min with OAuth2) is preferred; public JSON API (60 req/min) is automatic fallback when PRAW credentials are absent.
- **Rate limiting**: 0.5s delay for PTT, 1.0s for Reddit. Configurable via `--delay`.
- **Contrarian thresholds**: graduation ≥ 15% → extreme_fear signal; euphoria ≥ 15% → extreme_greed signal.
- **Buzz detection**: Z-score ≥ 2.0 flags anomaly; 30-period rolling window persisted to `data/buzz_history.json`.
- **Timezone**: Fixed to UTC+8 (Taiwan) for all timestamp parsing.

## Environment Variables

Secrets live in `.env` (never committed). See `.env.example` for template. Key vars:
- `INFLUXDB_TOKEN`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET` — InfluxDB connection
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` — Reddit OAuth2 (optional, enables PRAW)
- `INFLUXDB_RETENTION_DAYS` — Data retention (default 90)

## Grafana Alerts

Two pre-configured alert rules in `grafana/provisioning/alerting/alerts.yml`:
1. **Buzz Z-score > 3.0** — Potential pump-and-dump warning
2. **Euphoria ≥ 15%** — Market overheating signal
