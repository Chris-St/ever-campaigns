from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Ever Campaigns API"
    secret_key: str = "dev-ever-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = f"sqlite:///{BASE_DIR / 'ever_campaigns.db'}"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    public_api_url: str = "http://localhost:8000"
    public_web_url: str = "http://localhost:3000"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    self_funded_mode: bool = True
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_username: str = "EverAgentBia"
    reddit_password: str | None = None
    reddit_user_agent: str = "ever-agent:v1.0 (by /u/EverAgentBia)"
    reddit_bot_bio: str = (
        "I'm an AI agent that helps people find athletic gear. Powered by Ever for Bia. "
        "I only respond when I think I can genuinely help. Full disclosure in every reply."
    )
    demo_billing_mode: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
