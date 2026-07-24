# Pharma Catalyst Alert System

A production-ready web application that tracks 257 clinical-stage pharmaceutical companies and alerts you about upcoming high-impact events (FDA decisions, clinical trial readouts) that historically trigger major stock price movements.

**Current coverage:** 257 tickers, 592 events across 6 data sources, updated automatically.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Browser Dashboard                                │
│              Tailwind CSS · vanilla JS · FontAwesome                     │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │  GET /api/dashboard  (sub-50ms from cache)
                           │  POST /api/tickers   (scrapes immediately)
                           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (Python)                            │
│                                                                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌───────────────┐        │
│  │ Dashboard │  │ Tickers  │  │   Events     │  │  Notifications │        │
│  │  Routes   │  │  Routes  │  │   Routes     │  │   Routes       │        │
│  └────┬──────┘  └────┬─────┘  └──────┬───────┘  └───────┬───────┘        │
│       │              │               │                   │               │
│       ▼              ▼               ▼                   ▼               │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                    SQLite Database                                │    │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐               │    │
│  │  │  Ticker  │  │CatalystEvent │  │PriceSnapshot │               │    │
│  │  │  ticker  │  │ title        │  │ price, chg%  │               │    │
│  │  │  company │  │ event_date   │  │ updated_at   │               │    │
│  │  │  sector  │  │ impact_level  │  └──────────────┘               │    │
│  │  └──────────┘  │ alert_sent   │                                   │    │
│  │  ┌──────────┐  │ external_id  │  ┌──────────────┐               │    │
│  │  │ Aliases  │  │ source       │  │   (5 tables) │               │    │
│  │  └──────────┘  │ description  │  └──────────────┘               │    │
│  │                └──────────────┘                                   │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                    Background Scheduler (APScheduler)              │    │
│  │                                                                     │    │
│  │  ┌─────────────────────────────────┐  ┌────────────────────────┐  │    │
│  │  │  refresh_prices (5 min)         │  │  clinical_trials       │  │    │
│  │  │  yfinance → PriceSnapshot table │  │  pipeline (24h)        │  │    │
│  │  └─────────────────────────────────┘  │  CT.gov API → events   │  │    │
│  │                                       └────────────────────────┘  │    │
│  │  ┌─────────────────────────────────┐  ┌────────────────────────┐  │    │
│  │  │  PDUFA pipeline (60 min)        │  │  check_alerts (6h)     │  │    │
│  │  │  SEC Atom feed → 8-K/6-K →     │  │  7-day events →       │  │    │
│  │  │  Exhibit 99.1 → PDUFA extract  │  │  Discord / Telegram   │  │    │
│  │  └─────────────────────────────────┘  └────────────────────────┘  │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

## Data Sources

| Source | What it provides | Method | Frequency |
|---|---|---|---|
| **Yahoo Finance** (`yfinance`) | Live stock prices, daily change % | Scheduler → `PriceSnapshot` table | Every 5 min |
| **ClinicalTrials.gov** (API v2) | Phase 2/3 trial readouts, drug name, NCT ID, status | Sponsor-name search → match tracked tickers | Every 24h + on ticker creation |
| **SEC EDGAR** (Atom feed + exhibit download) | PDUFA target action dates from 8-K / 6-K filings | Atom feed → CIK→ticker match → Exhibit 99.1 download → regex date extraction | Every 60 min + catch-up on startup |
| **Seed data** (`seed_data.py`) | 34 hand-curated events with detailed backgrounds, drug mechanisms, trial context | Loaded once on first startup | — |
| **Known PDUFA calendar** (web-sourced) | Additional PDUFA dates found via web research | Manually added via API | As needed |
| **Ticker creation API** | Immediate ClinicalTrials.gov scrape for new tickers | `POST /api/tickers` triggers `_scrape_company()` | On demand |

### Key design decisions

1. **No on-demand API calls.** The dashboard never calls yfinance, ClinicalTrials.gov, or SEC during a user request. All data is pre-cached in SQLite tables by background jobs. Response times are sub-50ms regardless of upstream API status.

2. **Exhibit-based PDUFA extraction.** PDUFA dates aren't in the main 8-K form — they're in **Exhibit 99.1** (the press release attachment). The scraper lists the filing directory, identifies exhibit files by name pattern (`ex99*`, `ex-99*`), downloads them, and extracts dates via regex.

3. **6-K support for foreign companies.** Companies like Sanofi (SNY) file 6-K forms instead of 8-K. The pipeline monitors both form types.

4. **Alert deduplication.** Each event is alerted at most once — `alert_sent` timestamp prevents re-alerting on subsequent scheduler runs.

5. **Auto-generated aliases.** When a ticker is created, ClinicalTrials.gov sponsor aliases are auto-generated from the company name with punctuation stripping.

---

## Quick Start

### Prerequisites
- Python 3.11+
- pip

### Installation

```bash
cd pharma-alert
pip install -r requirements.txt

# Edit .env and add at least one notification channel:
#   DISCORD_WEBHOOK_URL=...
#   TELEGRAM_BOT_TOKEN=...
#   TELEGRAM_CHAT_ID=...
```

### Running

```bash
python main.py
```

Open **http://localhost:8000**. On first launch the database is automatically created, seeded with 34 hand-curated events, and the catch-up pipeline runs in the background (takes ~3 minutes to scan SEC for PDUFA filings).

---

## Dashboard Features

### Stock Table
All tracked tickers with live prices (updated every 5 min), daily change %, next catalyst event, impact level (color-coded), and countdown (red ≤7 days). Click any column header to sort, use the filter bar to search by ticker/name, impact level, or event type.

### Timeline View
Switch to **Timeline** for a month-grouped visual layout.

### Event Detail Modal
Click any event to see drug name, phase, trial ID, milestone, and background summary.

### Notifications
When Discord/Telegram is configured, a green bell icon appears in the nav bar. Automatic alerts fire for events ≤7 days away, once per event.

---

## Pipeline Details

### 1. Clinical Trials Pipeline (`scrapers/clinical_trials.py`)

```
ClinicalTrials.gov API v2 (free, no key required)
  │
  ├─ For each tracked ticker:
  │   ├─ Look up sponsor aliases from ticker_aliases table
  │   ├─ Search: query.term = "Vertex Pharmaceuticals"
  │   └─ Filter: Phase 2+, future/recent completion date
  │
  ├─ INSERT new studies as CatalystEvent rows
  └─ UPDATE existing studies (date, title, phase, description)
```

- Runs every 24 hours
- Also runs immediately when a new ticker is created
- Deduplicates by NCT ID (`external_id`)
- Updates existing events when trial dates slip

### 2. PDUFA Pipeline (`scrapers/pdufa.py`)

```
SEC EDGAR
  │
  ├─ CATCH-UP (first run only):
  │   ├─ Search: "PDUFA target action date" (2 year window)
  │   ├─ Paginate 20 pages → match tracked CIKs
  │   └─ Per-ticker fallback for missed companies
  │
  └─ ONGOING (every 60 min):
      ├─ SEC Atom feed: browse-edgar?type=8-K&type=6-K
      ├─ Parse CIK + ticker from feed title
      ├─ Match against tracked tickers
      ├─ Get filing directory listing
      ├─ Download Exhibit 99.1 (ex99* or ex-99* .htm files)
      ├─ Check for "PDUFA" keyword
      └─ Extract date + drug name via regex patterns:
           "assigned a PDUFA target action date of November 30, 2025"
           "PDUFA target action date is November 30, 2025"
```

- Filters out past dates (>30 days old)
- Creates events with `source = "sec_edgar_pdufa"` and `external_id = "SEC-{ticker}-{YYYYMMDD}"`
- Supports both 8-K (domestic) and 6-K (foreign company) filings
- KURA test case confirmed: Exhibit 99.1 correctly yields "ziftomenib" with "November 30, 2025"

### 3. Price Refresh (`services/price_service.py`)

- yfinance `history(period="5d")` for each ticker
- Writes to `PriceSnapshot` table (ticker PK, price, change %, timestamp)
- Dashboard reads exclusively from this table — no live yfinance calls
- Fallback prices hardcoded for all tracked tickers (used until first refresh)

### 4. Alert Engine (`services/notifier.py` + `tasks/scheduler.py`)

- `check_alerts()` runs every 6 hours
- Finds unsent events (alert_sent IS NULL) within 7-day window
- Sends via configured Telegram and/or Discord
- Sets `alert_sent = now()` to prevent re-alerting

---

## API Reference

### Tickers
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/tickers` | List all tracked tickers |
| `POST` | `/api/tickers` | Add ticker + auto-generate aliases + immediate CT.gov scrape |
| `DELETE` | `/api/tickers/{ticker}` | Remove ticker |

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
| `GET` | `/api/dashboard` | Full dashboard data (from PriceSnapshot + DB, no live API calls) |
| `GET` | `/api/dashboard/stats` | Summary: total, upcoming, alerting counts |

### Notifications
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/notify-status` | Which channels are configured |
| `POST` | `/api/test-notify` | Send a test notification |

---

## Adding a New Ticker

**From the UI** (recommended):
1. Click **"Add Ticker"** → enter symbol + company name
2. System auto-generates ClinicalTrials.gov aliases
3. Scrapes CT.gov for active Phase 2+ trials → inserts events (3-5 sec)
4. Dashboard shows ticker immediately with fallback price
5. Live price arrives within 5 minutes (scheduler refresh)

**From the API:**
```bash
curl -X POST http://localhost:8000/api/tickers \
  -H "Content-Type: application/json" \
  -d '{"ticker": "SNY", "company_name": "Sanofi S.A."}'
```

---

## Database Tables

| Table | Key Columns | Purpose |
|---|---|---|
| `tickers` | `ticker`, `company_name`, `sector` | Tracked companies |
| `catalyst_events` | `ticker`, `title`, `event_date`, `impact_level`, `description`, `alert_sent`, `external_id`, `source` | All events (seed, scraped, PDUFA, manual) |
| `price_snapshots` | `ticker` (PK), `price`, `change_percent`, `updated_at` | Cached live prices |
| `ticker_aliases` | `ticker_id`, `alias` | CT.gov sponsor search names |

**Event sources:** `manual` (seed), `clinicaltrials_gov`, `sec_edgar_pdufa`, `known_pdufa`

---

## Configuration

```ini
DATABASE_URL=sqlite:///./data/pharma_alerts.db
TELEGRAM_BOT_TOKEN=           # Create via @BotFather
TELEGRAM_CHAT_ID=
DISCORD_WEBHOOK_URL=          # Create in Discord channel settings
ALERT_DAYS_BEFORE=7           # Alert window (default 7 days)
BASE_URL=http://localhost:8000 # Used in notification links
```

---

## Project Structure

```
pharma-alert/
├── main.py                         # FastAPI entry point, startup hooks
├── .env                            # Environment variables
├── requirements.txt
├── README.md
├── app/
│   ├── config.py                   # pydantic-settings wrapper
│   ├── models/
│   │   ├── database.py             # SQLAlchemy ORM (5 tables) + auto-migrations
│   │   ├── schemas.py              # Pydantic request/response models
│   │   └── __init__.py
│   ├── routes/
│   │   ├── dashboard.py            # /api/dashboard, /stats, /test-notify, /notify-status
│   │   ├── tickers.py              # CRUD + auto-scrape on create
│   │   └── events.py               # CRUD
│   ├── services/
│   │   ├── price_service.py        # yfinance wrapper (scheduler only)
│   │   └── notifier.py             # Telegram + Discord sender
│   ├── tasks/
│   │   └── scheduler.py            # APScheduler: prices(5m), alerts(6h), trials(24h), PDUFA(60m)
│   └── templates/
│       └── dashboard.html          # Tailwind CSS dark-mode dashboard
├── scrapers/
│   ├── company_map.py              # Ticker → alias mapping (reads from DB)
│   ├── clinical_trials.py          # CT.gov API v2 scraper + pipeline
│   └── pdufa.py                    # SEC EDGAR PDUFA extractor (Atom feed + exhibit parser)
├── data/
│   └── seed_data.py                # 34 hand-curated events
└── scripts/
    └── add_tickers.py              # Batch ticker import script
```
