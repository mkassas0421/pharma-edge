"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/pharma_alerts.db"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""

    # ── Discord channel-specific webhooks ──
    discord_webhook_high_impact: str = ""
    discord_webhook_sec_live: str = ""
    discord_webhook_briefing: str = ""
    discord_webhook_clinical: str = ""
    discord_webhook_news: str = ""

    alert_days_before: int = 7
    refresh_interval_hours: int = 6
    base_url: str = "http://localhost:8000"
    timezone: str = "America/New_York"  # US East Coast market time

    # API key required on mutating endpoints (X-API-Key header).
    # Empty = mutating endpoints disabled (fail closed).
    api_key: str = ""

    # Sentry DSN for error tracking (empty = disabled, e.g. local dev)
    sentry_dsn: str = ""

    # Reaction capture: how many CALENDAR days after an event_date must pass
    # before we attempt to record its price reaction. Needs to cover T+5
    # trading days (~7-9 calendar days for a Friday event) plus margin.
    reaction_capture_min_days: int = 10

    # Minimum number of captured reactions before aggregate stats are shown
    # without a low-sample warning.
    reaction_min_sample_size: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
