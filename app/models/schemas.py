"""Pydantic schemas for request / response validation."""

import datetime
from pydantic import BaseModel, Field


# ── Ticker ──────────────────────────────────────────────────────────────────

class TickerCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10, description="Stock ticker symbol")
    company_name: str = Field(..., max_length=200)
    sector: str = "Biotechnology"
    notes: str = ""
    aliases: list[str] = Field(default_factory=list, description="ClinicalTrials.gov sponsor aliases (auto-generated if empty)")


class TickerResponse(BaseModel):
    id: int
    ticker: str
    company_name: str
    sector: str
    notes: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# ── Catalyst Event ──────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    ticker: str = Field(..., max_length=10)
    title: str = Field(..., max_length=300)
    event_type: str = Field(..., max_length=50)
    event_date: datetime.datetime
    impact_level: str = "High"
    description: str = ""


class EventResponse(BaseModel):
    id: int
    ticker: str
    title: str
    event_type: str
    event_date: datetime.datetime
    impact_level: str
    description: str
    source_url: str | None = None
    verified: bool = False

    class Config:
        from_attributes = True


# ── Dashboard (ticker + current price + next event) ─────────────────────────

class DashboardRow(BaseModel):
    ticker: str
    company_name: str
    current_price: float | None = None
    price_change_pct: float | None = None
    next_event_id: int | None = None
    next_event_title: str | None = None
    next_event_date: datetime.datetime | None = None
    next_event_type: str | None = None
    impact_level: str | None = None
    days_until_event: int | None = None
    next_event_description: str | None = None
