# Pharma Catalyst Alert System 🧬📊

A production-ready web application that tracks **228 clinical-stage pharmaceutical companies** and alerts you about upcoming high-impact events (FDA decisions, clinical trial readouts) that historically trigger major stock price movements.

> **Current coverage:** 228 tickers, 1000+ events across 6 data sources, updated automatically.

🔗 **Live demo:** [pharma-edge.onrender.com](https://pharma-edge.onrender.com)

---

## Features

- **✅ 228 tickers** — large-cap biotech to micro-cap pharma
- **✅ Live prices** — updated every 5 minutes (yfinance)
- **✅ 228 real fallback prices** — dashboard shows prices from the first load
- **✅ Automatic event discovery** — ClinicalTrials.gov + SEC EDGAR
- **✅ PDUFA date extraction** — from SEC 8-K/6-K filings, Exhibit 99.1
- **✅ 32 hand-curated seed events** — detailed drug descriptions & background (1000+ scraped events from CT.gov on top)
- **✅ Table + Timeline view** — sortable, filterable
- **✅ Event detail modal** — drug name, mechanism, phase, trial, analysis
- **✅ 5 Discord channels** — high-impact alerts, SEC filings, daily briefing, clinical updates, pharma news
- **✅ Pharma news feed** — Fierce Biotech, Fierce Pharma, GlobeNewswire every 15 min
- **✅ Daily morning & evening briefing** — cron-scheduled in configurable timezone
- **✅ SEC general filings monitor** — 8-K, 13D/13G, S-1/S-3 for tracked tickers every 30 min
- **✅ Subsidiary aliases** — large pharma subsidiaries (Janssen, Genzyme, etc.) mapped automatically
- **✅ Live alert banner** — red bar for events ≤7 days
- **✅ Dark mode dashboard** — Tailwind CSS, responsive, XSS-protected
- **✅ PostgreSQL + SQLite** — production / development modes
- **✅ Docker + Render deploy** — one-click deployment
- **✅ Alembic migrations** — database schema versioning
- **✅ Read-only dashboard** — users can't add/delete tickers from UI
- **✅ API rate limiting** — in-memory, 30 mutating requests per 60s per IP
- **✅ Health check with DB probe** — platform auto-restarts on database failure

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│            Browser Dashboard (Tailwind CSS + vanilla JS)      │
│  GET /api/dashboard  (<50ms, fully cached)                   │
│  POST /api/tickers   (instant, <50ms, no sync CT.gov scrape) │
└───────────────────────┬──────────────────────────────────────┘
                        │                    ▲
                        ▼                    │ Discord webhooks
┌──────────────────────────────────────────────────────────────┐
│               FastAPI Backend (Python 3.11)                   │
│  Rate-limiting middleware · XSS-protected templates            │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌─────────┐  │
│  │ Dashboard │  │ Tickers  │  │   Events     │  │Notific. │  │
│  │  Routes   │  │  Routes  │  │   Routes     │  │ Routes  │  │
│  └────┬──────┘  └────┬─────┘  └──────┬───────┘  └────┬────┘  │
│       ▼              ▼               ▼                ▼       │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  PostgreSQL (production) / SQLite (development)          │  │
│  │  5 tables: tickers, catalyst_events, price_snapshots,    │  │
│  │           ticker_aliases, alembic_version               │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │            Background Scheduler (APScheduler)             │  │
│  │  refresh_prices (5m)    │  clinical_trials (24h)        │  │
│  │  PDUFA pipeline (60m)   │  check_alerts (6h)            │  │
│  │  SEC filings feed (30m) │  news_feed (15m)              │  │
│  │  morning briefing (08:30)  │  evening briefing (21:00)   │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Design decisions

1. **No on-demand API calls.** All data is pre-cached by background jobs. Response times <50ms.
2. **Exhibit-based PDUFA extraction.** PDUFA dates are in **Exhibit 99.1**, not the main 8-K form.
3. **6-K support for foreign companies.** Pipeline monitors both 8-K (domestic) and 6-K (foreign).
4. **Alert deduplication.** Each event fired at most once (`alert_sent` timestamp).
5. **Auto-generated aliases.** CT.gov sponsor aliases generated from company name, plus hand-curated subsidiary names (Janssen, Genzyme, Wyeth, etc.).
6. **No sync CT.gov scrape on ticker creation.** The 24h background pipeline handles event discovery.
7. **Bounded in-memory dedup caches.** SEC filings (5000-entry FIFO) and news URLs (2000-entry FIFO) to prevent memory leaks.
8. **Rate-limited mutating endpoints.** 30 POST/DELETE requests per 60s per IP — returns HTTP 429.

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
| **0 sec** | 228 tickers on dashboard (228 real fallback prices) |
| **5-10 min** | Live prices arrive (yfinance 5-min cycle) |
| **~60 min** | 1000+ events from ClinicalTrials.gov pipeline (1s delay between tickers) |
| **24h** | Full sync complete, daily updates thereafter |

---

## Scheduler Jobs

| Job | Frequency | Description |
|---|---|---|
| `refresh_prices` | Every 5 min | yfinance → 228 tickers with 0.5s delay |
| `check_alerts` | Every 6 hours | Discord @everyone for High-impact events ≤7 days |
| `clinical_trials_pipeline` | Every 24 hours | CT.gov API v2 → new/updated events with 1s rate-limit delay |
| `pdufa_pipeline` | Every 60 min | SEC Atom feed → Exhibit 99.1 → new PDUFA dates |
| `sec_feed` | Every 30 min | SEC 8-K, 13D/13G, S-1/S-3 filings for tracked tickers (3s rate-limit between feeds) |
| `news_feed` | Every 15 min | Fierce Biotech, Fierce Pharma, GlobeNewswire RSS |
| `morning_briefing` | 08:30 (configurable TZ) | Daily radar: today's catalysts, weekly high-impact, pre-market movers |
| `evening_briefing` | 21:00 (configurable TZ) | Daily wrap: top gainers/losers, tomorrow's watchlist |

---

## Data Sources

| Source | What it provides | Frequency |
|---|---|---|
| **Yahoo Finance** (`yfinance`) | Live stock prices, daily change % | Every 5 min |
| **SEC EDGAR — PDUFA** (Atom feed) | PDUFA dates from 8-K/6-K Exhibit 99.1 | Every 60 min |
| **SEC EDGAR — General** (Atom feed) | 8-K, 13D/13G, S-1/S-3 filings for tracked tickers | Every 30 min |
| **RSS News Feeds** (feedparser) | Fierce Biotech, Fierce Pharma, GlobeNewswire Biotech | Every 15 min |
| **ClinicalTrials.gov** (API v2) | 1000+ **scraped** Phase 2/3 trial events (source: `clinicaltrials_gov`) | Every 24h |
| **Seed data** | 228 tickers + 32 **hand-curated** events with detailed drug backgrounds (source: `manual`) | First startup only |

---

## API Reference

### Tickers
| Method | Endpoint | Rate Limited | Description |
|---|---|---|---|
| `GET` | `/api/tickers` | No | List all tracked tickers |
| `POST` | `/api/tickers` | Yes (30/60s) | Add ticker (instant, no sync scrape) |
| `DELETE` | `/api/tickers/{ticker}` | Yes (30/60s) | Delete ticker (cascades to events, aliases, prices) |

### Events
| Method | Endpoint | Rate Limited | Description |
|---|---|---|---|
| `GET` | `/api/events` | No | List events (`?ticker=`, `?upcoming_only=true`) |
| `GET` | `/api/events/{id}` | No | Event detail |
| `POST` | `/api/events` | Yes (30/60s) | Create manual event |
| `DELETE` | `/api/events/{id}` | Yes (30/60s) | Delete event |

### Dashboard
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/dashboard` | Full dashboard data (cached, <50ms) |
| `GET` | `/api/dashboard/stats` | Summary counts |
| `GET` | `/` | HTML dashboard |
| `GET` | `/health` | Health check (probes DB connectivity) |

### Notifications
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/notify-status` | Which channels are configured (all 5 Discord + Telegram) |
| `POST` | `/api/test-notify` | Send test alert to #high-impact-catalysts |

---

## Dashboard

**Read-only** — no "Add Ticker" button, no delete icons. All user-supplied content is HTML-escaped to prevent XSS.

### Table columns
Ticker, Company, Price (228 real fallbacks), Change %, Next Catalyst (clickable), Date, Impact, Countdown

### Timeline view
Month-grouped visual layout with event type badges and countdown.

### Event detail modal
Drug name, mechanism, phase, trial name, milestone, and background analysis.

---

## Notifications

### 📡 Discord Multi-Channel System

Five dedicated channels:

| Channel | Content | Frequency | Ping |
|---|---|---|---|
| **#high-impact-catalysts** | PDUFA dates, Phase 3 readouts, FDA decisions | 1-3/day | ✅ `@everyone` |
| **#sec-filings-live** | 8-K, 13D/13G, S-1/S-3 filings for tracked tickers | 5-20+/day | ❌ |
| **#daily-biotech-briefing** | 🌅 Morning radar (08:30) + 🌙 Evening wrap (21:00) | 2/day fixed | ❌ |
| **#clinical-trials-updates** | Phase upgrades, date slips, CT.gov status changes | 3-10/day | ❌ |
| **#news-feed** | Fierce Biotech, Fierce Pharma, GlobeNewswire articles | 10-30/day | ❌ |

### SEC Filing Types Monitored

| Form | What it signals |
|---|---|
| **8-K** | Clinical results, FDA updates, material events |
| **6-K** | Foreign company equivalent of 8-K (SNY, AZN, NVS) |
| **13D** | Activist investor / >5% accumulation |
| **13G** | Passive institutional >5% ownership |
| **S-1** | IPO / new share registration (dilution risk) |
| **S-3** | Shelf registration (future dilution potential) |

### Large Pharma Subsidiary Aliases

To ensure the CT.gov scraper finds all relevant studies, major pharma tickers include hand-curated subsidiary names:

| Ticker | Subsidiary Aliases |
|---|---|
| **JNJ** | Janssen Research, Janssen Pharmaceutica, Janssen R&D |
| **PFE** | Wyeth, Pharmacia, Hospira |
| **MRK** | Merck Sharp & Dohme, MSD |
| **NVS** | Sandoz, Novartis Institutes |
| **AZN** | MedImmune, Acerta Pharma |
| **SNY** | Genzyme, Sanofi Pasteur |

### Setup

```ini
# Discord channel webhooks
DISCORD_WEBHOOK_HIGH_IMPACT=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_SEC_LIVE=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_BRIEFING=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_CLINICAL=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_NEWS=https://discord.com/api/webhooks/...

# App settings
ALERT_DAYS_BEFORE=7
TIMEZONE=America/New_York           # Market timezone for daily briefings
BASE_URL=https://pharma-edge.onrender.com
```

---

## Project Structure

```
pharma-alert/
├── main.py                         # FastAPI entry point, rate limiter, health check
├── Dockerfile                      # Container runtime (uses $PORT env var)
├── render.yaml                     # Render Blueprint with all env vars
├── .env.example                    # Env template with all webhooks
├── requirements.txt
├── alembic.ini                     # DB migrations
├── app/
│   ├── config.py                   # pydantic-settings (timezone, all webhooks)
│   ├── models/
│   │   ├── database.py             # SQLAlchemy ORM + Alembic auto-stamp
│   │   └── schemas.py              # Pydantic request/response models
│   ├── routes/
│   │   ├── dashboard.py            # Dashboard API + test-notify + notify-status
│   │   ├── tickers.py              # CRUD + auto-aliases + cascade delete
│   │   └── events.py               # CRUD
│   ├── services/
│   │   ├── price_service.py        # yfinance wrapper (browser UA)
│   │   └── notifier.py             # 5 Discord channels + Telegram + briefings
│   ├── tasks/
│   │   └── scheduler.py            # APScheduler: 8 background jobs
│   └── templates/
│       └── dashboard.html          # Tailwind CSS UI, XSS-protected
├── scrapers/
│   ├── company_map.py              # Alias management + subsidiary map
│   ├── clinical_trials.py          # CT.gov scraper + phase/date change detection
│   ├── pdufa.py                    # SEC EDGAR PDUFA extraction
│   ├── sec_filings.py              # SEC general filings monitor (bounded FIFO cache)
│   └── news_feed.py                # Pharma RSS news feed (bounded FIFO cache)
├── data/
│   └── seed_data.py                # 228 tickers + 32 curated events
├── alembic/
│   └── versions/
│       └── 001_initial.py          # Initial migration (4 tables)
└── scripts/
    ├── migrate.py                  # Migration commands (upgrade, check, history)
    └── add_tickers.py              # Batch ticker import via API
```

---

## Database

### Tables

| Table | Key columns | Purpose |
|---|---|---|
| `tickers` | `ticker`, `company_name`, `sector` | Tracked companies |
| `catalyst_events` | `ticker`, `title`, `event_date`, `impact_level`, `alert_sent`, `source`, `external_id` | All events |
| `price_snapshots` | `ticker` (PK), `price`, `change_percent` | Cached prices |
| `ticker_aliases` | `ticker_id`, `alias` | CT.gov search names (auto-gen + subsidiaries) |

### Supported RDBMS
- **SQLite** — development only, auto `create_all()` + Alembic stamp
- **PostgreSQL** — production, `alembic upgrade head` on startup

---

## Configuration

```ini
# Database
DATABASE_URL=sqlite:///./data/pharma_alerts.db  # or PostgreSQL URL

# Discord channel-specific webhooks (5 channels)
DISCORD_WEBHOOK_HIGH_IMPACT=    # PDUFA, Phase 3 — @everyone ping
DISCORD_WEBHOOK_SEC_LIVE=       # SEC filings (8-K, 13D, S-1)
DISCORD_WEBHOOK_BRIEFING=       # Daily morning radar + evening wrap
DISCORD_WEBHOOK_CLINICAL=       # CT.gov status/phase changes
DISCORD_WEBHOOK_NEWS=           # Pharma news (FierceBio, FiercePharma, GNW)

# Legacy fallback
DISCORD_WEBHOOK_URL=            # Used if channel-specific webhook is empty

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# App settings
ALERT_DAYS_BEFORE=7             # Alert window in days
REFRESH_INTERVAL_HOURS=6        # Alert check frequency
TIMEZONE=America/New_York       # Market timezone for daily briefings
BASE_URL=https://pharma-edge.onrender.com
```

---

## Performance

| Operation | Response time | Notes |
|---|---|---|
| Dashboard load | <50ms | Fully cached, single query for prices |
| Add ticker | <50ms | No sync CT.gov scrape |
| Price refresh (1 ticker) | 200-500ms | yfinance dependent |
| Full price cycle (228 tickers) | ~2 min | 0.5s delay between tickers |
| CT.gov pipeline (228 tickers) | ~4 min | 1s delay between tickers |
| SEC feed (6 form types) | ~20s | 3s delay between feeds |
| News feed (3 RSS sources) | ~3s | Parsed in parallel |

---

## FAQ

### How up-to-date is the data?
- **Prices:** every 5 minutes
- **PDUFA dates:** every 60 minutes
- **SEC general filings:** every 30 minutes
- **Pharma news:** every 15 minutes
- **Clinical trials:** every 24 hours
- **Alerts:** every 6 hours

### Do I need API keys?
**No.** ClinicalTrials.gov, yfinance, and SEC EDGAR are all free/public. Only Discord webhook requires registration (free).

### What if an API fails?
- **yfinance failure:** keeps existing price
- **CT.gov failure:** retries in 24 hours
- **SEC failure:** retries next cycle (30-60 min)
- **News feed failure:** retries in 15 minutes

### How do I add tickers?
Via API: `POST /api/tickers`. No "Add Ticker" button on the dashboard (read-only).

### Is the API rate-limited?
Yes — mutating endpoints (POST, DELETE on `/api/`) are limited to **30 requests per 60 seconds per IP**. Read endpoints are unrestricted.

### Why does the health check probe the database?
So Render can automatically restart the service if the database becomes unreachable. `/health` returns `{"status": "degraded", "database": "unreachable"}` on failure.

---

*Last updated: 2026-07-24 — 228 tickers, 1000+ events, 5 Discord channels, PostgreSQL + Docker + Render*
