# Pharma Catalyst Alert System — UML ábrák

Ez a dokumentum Mermaid szintaxisú UML ábrákkal mutatja be az alkalmazás pontos működését.
A Mermaid diagramok megjelennek a GitHub/GitLab webes nézetben, VS Code-ban (Mermaid Markdown
bővítménnyel) és a [mermaid.live](https://mermaid.live) oldalon.

---

## 1. Komponensdiagram — teljes architektúra

```mermaid
flowchart TB
    subgraph EX["🏢 Külső hivatalos források"]
        CT["ClinicalTrials.gov<br/>API v2 (studies)"]
        SEC["SEC EDGAR<br/>full-text search + Atom feed"]
        FR["Federal Register API<br/>FDA Notice of Meeting"]
        FDA["FDA Advisory Committee<br/>Calendar (HTML)"]
        YF["Yahoo Finance<br/>(yfinance, browser-UA)"]
        RSS["RSS feedek<br/>Fierce Biotech / Pharma,<br/>GlobeNewswire"]
    end

    subgraph RENDER["🚀 Render — egyetlen web service"]
        subgraph APP["FastAPI alkalmazás"]
            MID["Middleware<br/>api_key (legkülső) → rate_limit"]
            ROUTES["Route-ok<br/>dashboard · tickers · events · reactions"]
            CACHE["TTLCache<br/>dashboard 60s · stats 120s"]
            SCHED["APScheduler<br/>10 intervallum-job + 5 egyszeri + 2 cron"]
            SCRAPERS["Scraperek<br/>clinical_trials · pdufa · sec_filings<br/>news_feed · federal_register · fda_adcom"]
            SVC["Szolgáltatások<br/>price_service · reaction_service · notifier"]
        end
        DB[("PostgreSQL<br/>6 tábla")]
    end

    subgraph NOTIF["🔔 Értesítési csatornák"]
        DC_HI["Discord<br/>#high-impact-catalysts"]
        DC_SEC["Discord<br/>#sec-filings-live"]
        DC_CL["Discord<br/>#clinical-trials-updates"]
        DC_BR["Discord<br/>#daily-biotech-briefing"]
        DC_NEWS["Discord<br/>#news-feed"]
    end

    B["🌐 Böngésző<br/>dashboard.html (Tailwind + JS)"]

    B -->|"GET / , GET /api/*"| MID
    MID --> ROUTES
    ROUTES --> CACHE
    ROUTES --> DB
    SCHED --> SCRAPERS
    SCHED --> SVC
    SVC --> DB
    SCRAPERS --> CT
    SCRAPERS --> SEC
    SCRAPERS --> FR
    SCRAPERS --> FDA
    SVC -->|"fetch_price_and_change /<br/>get_historical_prices"| YF
    SCRAPERS --> RSS
    SVC -->|"POST embedek"| DC_HI
    SVC -->|"POST embedek"| DC_SEC
    SVC -->|"POST embedek"| DC_CL
    SVC -->|"POST embedek"| DC_BR
    SVC -->|"POST embedek"| DC_NEWS
```

**Működési elv:** minden adat *előre* gyűjtött — a dashboard soha nem hív élőben külső API-t.
A scraperek a hivatalos forrásokból töltik a `catalyst_events` táblát, az APScheduler 5 percenként
frissíti az árakat, a riasztásokat pedig a scheduler küldi Discord webhookokra. Minden esemény
`source_url`-lel és `verified=True` flaggel rendelkezik (kizárólag hivatalos források elve).

---

## 2. Osztálydiagram — adatmodell (SQLAlchemy ORM)

```mermaid
classDiagram
    direction LR

    class Ticker {
        +int id PK
        +str ticker  unique, index
        +str company_name
        +str sector
        +str notes
        +datetime created_at
    }

    class TickerAlias {
        +int id PK
        +int ticker_id
        +str alias
        +datetime created_at
    }

    class CatalystEvent {
        +int id PK
        +int ticker_id
        +str ticker  denormalizált
        +str title
        +str event_type
        +datetime event_date  index
        +str impact_level
        +str description
        +datetime alert_sent  null = még nem riasztva
        +str external_id  NCT / SEC- / FR- / FDA-ADCOM-
        +str source
        +str source_url  hivatalos forrás link
        +bool verified
        +datetime created_at
    }

    class PriceSnapshot {
        +str ticker PK
        +float price
        +float change_percent
        +datetime updated_at
    }

    class ScraperDedup {
        +int id PK
        +str source  sec_filings | news_feed
        +str identifier
        +datetime seen_at
        +UniqueConstraint(source, identifier)
    }

    class EventReaction {
        +int id PK
        +int event_id  unique
        +str ticker  denormalizált
        +float price_before
        +float price_at_event
        +float price_after_1d
        +float price_after_5d
        +float reaction_1d_pct
        +float reaction_5d_pct
        +str event_type  denormalizált
        +str impact_level  denormalizált
        +str status  pending | captured | failed
        +datetime captured_at
        +UniqueConstraint(event_id)
    }

    Ticker "1" --> "*" TickerAlias : "ticker_id (nincs FK, kézi törlés)"
    Ticker "1" --> "*" CatalystEvent : "ticker_id (nincs FK)"
    CatalystEvent "1" --> "0..1" EventReaction : "event_id (nincs FK)"
    Ticker "1" --> "1" PriceSnapshot : "denormalizált ticker"
```

**Fontos tervezési döntések:**
- **Nincs FK megszorítás** — a kódbázis konvenciója szerint a kapcsolatok logikaiak, a törlés
  kézi kaszkád (lásd `delete_ticker`).
- **Denormalizáció** — `catalyst_events.ticker` és az `event_reactions` metaadatai (ticker,
  event_type, impact_level) azért duplikáltak, hogy az esemény pruning után is fennmaradjon a
  reakció-statisztika.
- **`ScraperDedup`** — a csak-értesítő scraperek (SEC feed, news) restart után sem küldenek
  újra régi tételeket; az in-memory `BoundedSet` csak gyorsítótár felette.
- **Uniqe megszorítások** — `(source, identifier)` és `event_id` — duplikátum-biztosítás.

---

## 3. Szekvenciadiagram — rendszerindítás (lifespan)

```mermaid
sequenceDiagram
    participant R as Render (uvicorn)
    participant A as FastAPI lifespan
    participant DB as PostgreSQL
    participant S as APScheduler

    R->>A: indítás
    A->>DB: init_db() — alembic upgrade head
    A->>DB: cleanup_fabricated() — fabrikált események törlése
    A->>DB: seed_database() — 295 ticker (ha hiányzik)
    A->>DB: seed_aliases() — leányvállalati aliasok
    A->>DB: backfill_source_urls() — meglévő események forráslinkjei (idempotens)
    A->>S: start_scheduler()
    S->>S: seed_snapshots() — fallback árak (228 ticker)
    S-->>S: egyszeri jobok késleltetéssel
    S->>S: +30s clinical_trials pipeline
    S->>S: +35s pdufa pipeline (catch-up 2 év)
    S->>S: +45s federal_register pipeline
    S->>S: +55s fda_adcom pipeline
    S->>S: +65s capture_event_reactions (első backfill ~600 esemény)
    S-->>A: yield — az alkalmazás fut
```

---

## 4. Szekvenciadiagram — dashboard lekérés

```mermaid
sequenceDiagram
    participant B as Böngésző
    participant A as FastAPI (GET /api/dashboard)
    participant C as TTLCache (60s)
    participant DB as PostgreSQL

    B->>A: GET /api/dashboard
    A->>C: dashboard_cache.get("dashboard")
    alt cache találat
        C-->>A: tárolt válasz
    else cache miss
        A->>DB: 1) összes ticker (order by ticker)
        A->>DB: 2) összes PriceSnapshot
        A->>DB: 3) következő esemény tickerenként (min-date subquery + join)
        A->>C: dashboard_cache.set("dashboard", result)
    end
    A-->>B: JSON rows (ár + következő katalizátor + napok hátra)
```

**Cache érvénytelenítés:** ticker/esemény CRUD, ár-frissítés és pruning mind `invalidate_all()`-t
hív — a dashboard ilyenkor legfeljebb 60 másodpercig mutat régi adatot. Nincs N+1 lekérdezés,
három bulk query az egész válasz.

---

## 5. Szekvenciadiagram — API védelem (middleware sorrend)

A Starlette-ben az **utoljára** regisztrált middleware a legkülső. Ezért: `api_key` fut először,
utána a `rate_limit` — a jogosulatlan kérések 401-et kapnak, mielőtt a közös per-IP bucket-be
számítanának.

```mermaid
sequenceDiagram
    participant B as Kliens
    participant A as api_key middleware
    participant R as rate_limit middleware
    participant H as Route (POST /api/tickers)
    participant DB as PostgreSQL

    B->>A: POST /api/tickers + X-API-Key fejléc
    alt API_KEY nincs konfigurálva a szerveren
        A-->>B: 503 — mutáló végpontok letiltva (fail closed)
    else hiányzó / rossz kulcs
        A-->>B: 401
    else érvényes kulcs
        A->>R: call_next
        R->>R: IP bucket (X-Forwarded-For első eleme)
        alt több mint 30 mutáló kérés 60s alatt
            R-->>B: 429
        else
            R->>H: route
            H->>DB: ticker INSERT + aliasok generálása
            H-->>B: 201 Created
        end
    end
```

**Kivételek:** a GET végpontok publikusak (a dashboard linkkel bárki nézhető); a rate limit a
`/api/*` összes POST/DELETE kérésére vonatkozik.

---

## 6. Szekvenciadiagram — ár-frissítés (5 percenként)

```mermaid
sequenceDiagram
    participant S as APScheduler (refresh_prices)
    participant Y as Yahoo Finance (yfinance)
    participant DB as PostgreSQL
    participant C as TTLCache

    S->>DB: összes ticker listája
    loop minden ticker — 0.5s szünet a rate limit miatt
        S->>Y: fetch_price_and_change(ticker) — 5 napos history
        alt ár érkezett
            S->>DB: upsert PriceSnapshot (delete + insert)
        else nincs ár (rate limit / hiba)
            Note over S, DB: meglévő DB érték marad érvényben
        end
    end
    S->>C: dashboard_cache.invalidate_all()
```

---

## 7. Szekvenciadiagram — riasztás küldése (6 óránként)

```mermaid
sequenceDiagram
    participant S as APScheduler (check_alerts)
    participant DB as PostgreSQL
    participant N as notifier
    participant D as Discord webhook

    S->>DB: események: event_date >= most ÉS <= most+7nap ÉS alert_sent IS NULL
    alt van el nem küldött esemény
        S->>DB: cégnevek batch lekérdezése (nincs N+1)
        loop minden esemény
            S->>N: send_alert(...)
            N->>D: POST embed → #high-impact-catalysts (@everyone)
            alt sikeres küldés
                N-->>S: True
                S->>DB: alert_sent = most (egyszeri riasztás garantált)
            else sikertelen ÉS legacy webhook konfigurálva
                N->>D: POST embed → legacy webhook
            end
        end
    end
```

**Kulcsszabály:** minden esemény legfeljebb egyszer kap riasztást — az `alert_sent` timestamp
zárja le; a klinikai pipeline az UPDATE-nél ezt a mezőt megőrzi.

---

## 8. Szekvenciadiagram — klinikai trial pipeline (példa: esemény-felfedező scraper)

```mermaid
sequenceDiagram
    participant S as APScheduler (24h + startup)
    participant CT as ClinicalTrials.gov API v2
    participant DB as PostgreSQL
    participant N as notifier
    participant D as Discord

    loop minden ticker — 1s szünet
        S->>S: search_terms(ticker) — aliasok a ticker_aliases táblából
        S->>CT: GET /api/v2/studies (term, pageSize 30)
        CT-->>S: tanulmányok JSON
        S->>DB: létezik-e external_id (NCT) + ticker páros?
        alt új tanulmány
            S->>DB: INSERT CatalystEvent (verified=True, source_url=NCT link)
        else meglévő tanulmány
            S->>DB: UPDATE mezők (event_date, title, phase, impact) — alert_sent marad
            S->>S: _detect_change — fázis-upgrade vagy >30 nap dátumcsúszás?
        end
    end
    Note over S: db.commit() — minden feldolgozás után
    alt van változás és webhook konfigurálva
        S->>N: send_clinical_change (batchelt)
        N->>D: POST embed → #clinical-trials-updates
    end
```

**Ugyanez az upsert minta** fut a PDUFA pipeline-ban (`external_id = SEC-{ticker}-{dátum}`),
a Federal Register pipeline-ban (`FR-{document_number}` + `(source, ticker, event_date)`
duplikátum-szűrés) és az FDA AdCom scraperben (`FDA-ADCOM-{ticker}-{dátum}`).
A SEC filings feed és a news feed **nem tárol eseményt** — csak Discord-ra küld,
`scraper_dedup` táblával deduplikálva.

---

## 9. Szekvenciadiagram — reakció-rögzítés (napi 1×)

```mermaid
sequenceDiagram
    participant S as APScheduler (capture_event_reactions)
    participant DB as PostgreSQL
    participant Y as Yahoo Finance (yfinance)

    S->>DB: érett események: event_date <= most−10 nap ÉS (nincs reakció-sor VAGY status != captured)
    alt nincs érett esemény
        Note over S: kilép
    else
        loop minden érett esemény — 0.5s szünet
            S->>Y: get_historical_prices(ticker, event_date) — T−1 / T / T+1 / T+5 záróárak
            alt minden ár None (delist / hiba)
                S->>DB: EventReaction status = failed — következő ciklusban újra
            else T+5 záróár elérhető
                S->>DB: status = captured, reaction_1d_pct / reaction_5d_pct kiszámolva
            else T+5 még hiányzik (esemény túl friss)
                S->>DB: status = pending — következő ciklusban újra
            end
        end
        Note over S: db.commit()
    end
```

**A 10 napos küszöb** (`reaction_capture_min_days`) lefedi a T+5 kereskedési napot
(pénteki eseménynél ~7–9 naptári nap) plusz tartalékot.

---

## 10. Állapotdiagram — EventReaction életciklusa

```mermaid
stateDiagram-v2
    [*] --> pending : esemény érett (event_date ≤ most−10 nap)
    pending --> captured : T+5 záróár megvan, reakció % rögzítve
    pending --> failed : egyetlen ár sem érhető el (delist / yfinance hiba)
    failed --> pending : következő napi ciklus — újrapróbálás
    failed --> captured : későbbi ciklusban T+5 elérhetővé válik
    captured --> [*] : végállapot — denormalizált adatok megmaradnak
```

---

## 11. Állapotdiagram — CatalystEvent életciklusa

```mermaid
stateDiagram-v2
    [*] --> unsent : scraper INSERT (verified=True, source_url)
    unsent --> alerted : check_alerts sikeres Discord küldés → alert_sent = most
    alerted --> [*] : prune 90 nap után (reakció lezárt)
    unsent --> [*] : prune 365 nap után (ancient — reakció nélkül is)
    unsent --> updated : scraper UPDATE (dátum/cím változhat) — alert_sent megőrizve
    updated --> unsent
    updated --> alerted
```

**Pruning szabály:** a 90 napnál régebbi esemény csak akkor törlődik, ha a reakció-sora
végleges (`captured` vagy `failed`); a 365 napnál régebbi mindenképp törlődik
(`prune_expired_events`, naponta).

---

## 12. Tevékenységábra — esemény-feldolgozó scraper általános folyamata

```mermaid
flowchart TD
    A([Scheduler indít]Job) --> B{Van konfigurálva<br/>a webhook / source?}
    B -- nem --> Z([Kilépés])
    B -- igen --> C[Forrás lekérése<br/>API / Atom feed / RSS / HTML]
    C --> D{Sikeres<br/>lekérés?}
    D -- nem --> E[log + hiba]
    E --> Z
    D -- igen --> F[Dedup ellenőrzés<br/>external_id / URL / (source, ticker, date)]
    F --> G{Már láttuk?}
    G -- igen --> H[UPDATE / skip]
    H --> I{Érdemi változás?<br/>fázis-upgrade, >30 nap csúszás}
    I -- nem --> Z
    I -- igen --> J[Discord értesítés küldése]
    G -- nem --> K[INSERT CatalystEvent<br/>source_url + verified=True]
    K --> L[Cache invalidation<br/>dashboard + stats]
    J --> Z
    L --> Z
```

---

## Melléklet A — Scheduler job-ok összefoglaló táblázata

| Job ID | Gyakoriság | Feladat |
|---|---|---|
| `refresh_prices` | 5 perc | yfinance árak → `price_snapshots` |
| `check_alerts` | 6 óra | küszöbön álló események riasztása (egyszer) |
| `clinical_trials_pipeline` | 24 óra (+ egyszer +30s) | CT.gov upsert, fázis/dátum változások |
| `pdufa_pipeline` | 60 perc (+ egyszer +35s) | SEC 8-K/6-K PDUFA dátumok (először 2 éves catch-up) |
| `sec_feed` | 30 perc | SEC filing feed → `#sec-filings-live` (csak értesítés) |
| `news_feed` | 60 perc | RSS cikkek → `#news-feed` (csak értesítés) |
| `federal_register_pipeline` | 12 óra (+ egyszer +45s) | FDA AdCom ülések a Federal Register-ből |
| `fda_adcom_pipeline` | 24 óra (+ egyszer +55s) | FDA kalendárium (jelenleg üres HTML — degradálódik) |
| `prune_events` | 24 óra | 90/365 napos esemény-törlés (reakció-védett) |
| `capture_event_reactions` | 24 óra (+ egyszer +65s) | érett események árfolyam-reakcióinak rögzítése |
| `morning_briefing` / `evening_briefing` | cron 08:30 / 21:00 (beállított időzóna) | napi összefoglaló (csak ha briefing webhook van) |

## Melléklet B — API végpontok

| Módszer | Útvonal | Auth | Leírás |
|---|---|---|---|
| GET | `/` | — | Dashboard HTML (Jinja2) |
| GET | `/health` | — | DB probe + scheduler állapot |
| GET | `/api/dashboard` | — | Tickerek + ár + következő esemény (60s cache) |
| GET | `/api/dashboard/stats` | — | Összesített számlálók (120s cache) |
| GET | `/api/tickers` | — | Ticker lista |
| POST | `/api/tickers` | API kulcs | Új ticker + alias generálás |
| DELETE | `/api/tickers/{ticker}` | API kulcs | Törlés kézi kaszkáddal |
| GET | `/api/events` | — | Események (ticker / upcoming szűrő) |
| GET | `/api/events/{id}` | — | Egy esemény részletei |
| POST | `/api/events` | API kulcs | Új esemény |
| DELETE | `/api/events/{id}` | API kulcs | Esemény törlése |
| GET | `/api/events/{id}/reaction` | — | Rögzített reakció egy eseményhez |
| GET | `/api/reactions/stats` | — | Reakció-statisztikák (szűrőkkel) |
| GET | `/api/reactions/stats/similar/{id}` | — | Kohorsz-statisztika (ticker+type → ticker → market) |
| POST | `/api/test-notify` | API kulcs | Teszt riasztás |
| GET | `/api/notify-status` | — | Konfigurált csatornák állapota |
