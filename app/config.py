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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
