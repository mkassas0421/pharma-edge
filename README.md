# Pharma Catalyst Alert System 🧬📊

A production-ready web application that tracks **295 clinical-stage pharmaceutical companies** and alerts you about upcoming high-impact events (FDA decisions, clinical trial readouts) that historically trigger major stock price movements.

> **Current coverage:** 295 tickers, 1000+ events across 6 data sources, updated automatically.

🔗 **Live demo:** [pharma-edge.onrender.com](https://pharma-edge.onrender.com)

---

## Features

- **✅ 295 tickers** — large-cap biotech to micro-cap pharma
- **✅ Live prices** — updated every 5 minutes (yfinance)
- **✅ 228 real fallback prices** — dashboard shows prices from the first load
- **✅ Automatic event discovery** — ClinicalTrials.gov + SEC EDGAR
- **✅ PDUFA date extraction** — from SEC 8-K/6-K filings, Exhibit 99.1
- **✅ 34 hand-curated events** — detailed drug descriptions & background
- **✅ Table + Timeline view** — sortable, filterable
- **✅ Event detail modal** — drug name, mechanism, phase, trial, analysis
- **✅ 4 Discord channels** — high-impact alerts, SEC filings, daily briefing, clinical updates
- **✅ Daily morning & evening briefing** — cron-scheduled market radar
- **✅ Live alert banner** — red bar for events ≤7 days
- **✅ Discord notifications** — automatic push alerts
- **✅ Dark mode dashboard** — Tailwind CSS, responsive
- **✅ PostgreSQL + SQLite** — production / development modes
- **✅ Docker + Render deploy** — one-click deployment
- **✅ Alembic migrations** — database schema versioning
- **✅ Read-only dashboard** — users can't add/delete tickers from UI

---

## Architecture

```
Browser Dashboard (Tailwind CSS · vanilla JS · FontAwesome)
       │
       │  GET /api/dashboard  (<50ms cached)
       │  POST /api/tickers   (instant, <50ms, no sync CT.gov scrape)
       ▼
┌──────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (Python 3.11)                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ Dashboard │  │ Tickers  │  │   Events     │  │Notific. │ │
│  │  Routes   │  │  Routes  │  │   Routes     │  │ Routes  │ │
│  └────┬──────┘  └────┬─────┘  └──────┬───────┘  └────┬────┘ │
│       ▼              ▼               ▼                ▼       │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │   PostgreSQL (production) / SQLite (development)          │ │
│  │   5 tables: tickers, catalyst_events, price_snapshots,    │ │
│  │            ticker_aliases, alembic_version                │ │
│  └──────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │          Background Scheduler (APScheduler)               │ │
│  │  refresh_prices (5m) │ clinical_trials (24h)             │ │
│  │  PDUFA pipeline (60m) │ check_alerts (6h)                │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Design decisions

1. **No on-demand API calls.** All data is pre-cached by background jobs. Response times <50ms.
2. **Exhibit-based PDUFA extraction.** PDUFA dates are in **Exhibit 99.1**, not the main 8-K form.
3. **6-K support for foreign companies.** Pipeline monitors both 8-K (domestic) and 6-K (foreign).
4. **Alert deduplication.** Each event fired at most once (`alert_sent` timestamp).
5. **Auto-generated aliases.** CT.gov sponsor aliases generated from company name.
6. **No sync CT.gov scrape on ticker creation.** The 24h background pipeline handles event discovery.

---

## Quick Start

### Local development (SQLite)

```bash
cd pharma-alert
pip install -r requirements.txt
python main.py
# → http://localhost:8000
```

### Production (PostgreSQL)

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/db
python scripts/migrate.py
python main.py
```

### Docker

```bash
docker build -t pharma-alert .
docker run -p 8000:8000 -e DATABASE_URL="..." pharma-alert
```

---

## Deployment Timeline (first startup)

| Time | What happens |
|---|---|
| **0 sec** | 295 tickers on dashboard (228 real prices, 67 delisted = `--`) |
| **5-10 min** | Live prices arrive (yfinance 5-min cycle) |
| **~60 min** | 1000+ events from ClinicalTrials.gov pipeline |
| **24h** | Full sync complete, daily updates thereafter |

---

## Data Sources

| Source | What it provides | Frequency |
|---|---|---|
| **Yahoo Finance** (`yfinance`) | Live stock prices, daily change % | Every 5 min |
| **ClinicalTrials.gov** (API v2) | Phase 2/3 trial readouts | Every 24h |
| **SEC EDGAR — PDUFA** (Atom feed) | PDUFA dates from 8-K/6-K Exhibit 99.1 | Every 60 min |
| **SEC EDGAR — General** (Atom feed) | 8-K, 13D/13G, S-1/S-3 filings for tracked tickers | Every 30 min |
| **Seed data** | 295 tickers + 34 hand-curated events | First startup only |

---

## API Reference

### Tickers
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tickers` | List all tracked tickers |
| `POST` | `/api/tickers` | Add ticker (instant, no sync scrape) |
| `DELETE` | `/api/tickers/{ticker}` | Delete ticker |

### Events
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/events` | List events (`?ticker=`, `?upcoming_only=true`) |
| `GET` | `/api/events/{id}` | Event detail |
| `POST` | `/api/events` | Create manual event |
| `DELETE` | `/api/events/{id}` | Delete event |

### Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/dashboard` | Full dashboard data (cached, <50ms) |
| `GET` | `/api/dashboard/stats` | Summary counts |
| `GET` | `/` | HTML dashboard |
| `GET` | `/health` | Health check |

### Notifications
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/notify-status` | Which channels are configured |
| `POST` | `/api/test-notify` | Send test alert (no UI button) |

---

## Dashboard

**Read-only** — no "Add Ticker" button, no delete icons.

### Table columns
Ticker, Company, Price (228 real fallbacks), Change %, Next Catalyst (clickable), Date, Impact, Countdown

### Timeline view
Month-grouped visual layout with event type badges and countdown.

### Event detail modal
Drug name, mechanism, phase, trial name, milestone, and background analysis.

---

## Notifications

### 📡 Discord Multi-Channel System

Four dedicated channels, each with a specific purpose:

| Channel | Content | Frequency | Ping |
|---|---|---|---|
| **#high-impact-catalysts** | PDUFA dates, Phase 3 readouts, FDA decisions | 1-3/day | ✅ `@everyone` |
| **#sec-filings-live** | 8-K, 13D/13G, S-1/S-3 filings for tracked tickers | 5-20+/day | ❌ |
| **#daily-biotech-briefing** | 🌅 Morning radar (08:30 UTC) + 🌙 Evening wrap (21:00 UTC) | 2/day fixed | ❌ |
| **#clinical-trials-updates** | Phase upgrades, date slips, status changes on CT.gov | 3-10/day | ❌ |

### SEC Filing Types Monitored

| Form | What it signals |
|---|---|
| **8-K** | Clinical results, FDA updates, material events |
| **6-K** | Foreign company equivalent of 8-K (SNY, AZN, NVS) |
| **13D** | Activist investor / >5% accumulation |
| **13G** | Passive institutional >5% ownership |
| **S-1** | IPO / new share registration (dilution risk) |
| **S-3** | Shelf registration (future dilution potential) |

### Setup

```ini
# Discord channel webhooks
DISCORD_WEBHOOK_HIGH_IMPACT=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_SEC_LIVE=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_BRIEFING=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_CLINICAL=https://discord.com/api/webhooks/...

# Telegram (optional)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
ALERT_DAYS_BEFORE=7
```

---

## Project Structure

```
pharma-alert/
├── main.py                         # FastAPI entry point
├── Dockerfile                      # Container runtime
├── render.yaml                     # Render Blueprint
├── .env.example                    # Env template
├── requirements.txt
├── alembic.ini                     # DB migrations
├── app/
│   ├── config.py                   # pydantic-settings
│   ├── models/
│   │   ├── database.py             # SQLAlchemy ORM
│   │   └── schemas.py              # Pydantic models
│   ├── routes/
│   │   ├── dashboard.py            # Dashboard API
│   │   ├── tickers.py              # CRUD
│   │   └── events.py               # CRUD
│   ├── services/
│   │   ├── price_service.py        # yfinance wrapper
│   │   └── notifier.py             # Discord + Telegram
│   ├── tasks/
│   │   └── scheduler.py            # APScheduler
│   └── templates/
│       └── dashboard.html          # Tailwind CSS UI
├── scrapers/
│   ├── company_map.py              # Alias management
│   ├── clinical_trials.py          # CT.gov scraper + change detection
│   ├── pdufa.py                    # SEC EDGAR PDUFA extraction
│   └── sec_filings.py              # SEC general filings monitor (8-K, 13D, S-1)
├── data/
│   └── seed_data.py                # 295 tickers + 34 events
├── alembic/
│   └── versions/
│       └── 001_initial.py          # Initial migration
└── scripts/
    └── migrate.py                  # Migration commands
```

---

## Database

### Tables

| Table | Key columns | Purpose |
|---|---|---|
| `tickers` | `ticker`, `company_name`, `sector` | Tracked companies |
| `catalyst_events` | `ticker`, `title`, `event_date`, `impact_level` | All events |
| `price_snapshots` | `ticker` (PK), `price`, `change_percent` | Cached prices |
| `ticker_aliases` | `ticker_id`, `alias` | CT.gov search names |

### Supported RDBMS
- **SQLite** — development only, auto `create_all()`
- **PostgreSQL** — production, `alembic upgrade head` on startup

---

## Configuration

```ini
DATABASE_URL=sqlite:///./data/pharma_alerts.db  # or PostgreSQL URL
DISCORD_WEBHOOK_URL=                             # Discord notifications
TELEGRAM_BOT_TOKEN=                              # Telegram (optional)
TELEGRAM_CHAT_ID=                                # Telegram (optional)
ALERT_DAYS_BEFORE=7                              # Alert window
REFRESH_INTERVAL_HOURS=6                         # Alert check frequency
BASE_URL=http://localhost:8000                    # Dashboard URL
```

---

## Development

### Add a ticker

```bash
curl -X POST http://localhost:8000/api/tickers \
  -H "Content-Type: application/json" \
  -d '{"ticker": "SNY", "company_name": "Sanofi S.A."}'
```

Instant (<50ms). CT.gov events are picked up by the 24h pipeline.

### Migrations

```bash
python scripts/migrate.py           # upgrade to latest
python scripts/migrate.py --check   # check pending
python scripts/migrate.py --history # show history
```

### Seed data

`data/seed_data.py` contains 295 tickers + 34 curated events (Jul-Dec 2026), each with detailed drug mechanism and market context.

---

## Performance

| Operation | Response time | Notes |
|---|---|---|
| Dashboard load | <50ms | Fully cached |
| Add ticker | <50ms | No sync CT.gov scrape |
| Price refresh (1 ticker) | 200-500ms | yfinance dependent |
| Full price cycle (295 tickers) | ~2.5 min | 0.5s delay between |
| CT.gov pipeline (295 tickers) | ~60 min | 1s delay between |

---

## FAQ

### How up-to-date is the data?
- **Prices:** every 5 minutes
- **PDUFA dates:** every 60 minutes
- **Clinical trials:** every 24 hours
- **Alerts:** every 6 hours

### Do I need API keys?
**No.** ClinicalTrials.gov, yfinance, and SEC EDGAR are all free/public. Only Discord webhook requires registration (free).

### What if an API fails?
- **yfinance failure:** keeps existing price
- **CT.gov failure:** retries in 24 hours
- **SEC failure:** retries in 60 minutes

### How do I add tickers?
Via API: `POST /api/tickers`. No "Add Ticker" button on the dashboard (read-only).

### Why are 67 tickers showing `--`?
Those are delisted companies no longer trading ($ACLX, $ADVM, $AKRO, etc.).

---

*Last updated: 2026-07-24 — 295 tickers, 1000+ events, PostgreSQL + Docker + Render*
