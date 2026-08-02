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


# ── Event Reaction ─────────────────────────────────────────────────────────

class EventReactionResponse(BaseModel):
    id: int
    event_id: int
    ticker: str
    price_before: float | None = None
    price_at_event: float | None = None
    price_after_1d: float | None = None
    price_after_5d: float | None = None
    reaction_1d_pct: float | None = None
    reaction_5d_pct: float | None = None
    event_type: str | None = None
    impact_level: str | None = None
    indication: str | None = None
    status: str
    captured_at: datetime.datetime | None = None

    class Config:
        from_attributes = True


class ReactionStatsResponse(BaseModel):
    n: int
    mean_1d_pct: float | None = None
    median_1d_pct: float | None = None
    stdev_1d_pct: float | None = None
    mean_5d_pct: float | None = None
    median_5d_pct: float | None = None
    stdev_5d_pct: float | None = None
    positive_rate_1d: float | None = None
    max_1d_pct: float | None = None
    min_1d_pct: float | None = None
    low_sample_warning: bool = False


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
