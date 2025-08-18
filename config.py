from __future__ import annotations

"""Configuration loader for the Discord Yahoo Fantasy bot."""

from pydantic import BaseSettings, AnyUrl


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DISCORD_TOKEN: str
    AUTH_BASE_URL: AnyUrl = "http://localhost:8000"
    PUBLIC_BASE_URL: AnyUrl = "http://localhost:8000"
    YAHOO_CLIENT_ID: str
    YAHOO_CLIENT_SECRET: str
    YAHOO_REDIRECT_PATH: str = "/auth/callback"
    PORT: int = 8000

    @property
    def redirect_uri(self) -> str:
        """Full redirect URI Yahoo sends the user back to."""
        return f"{self.PUBLIC_BASE_URL.rstrip('/')}{self.YAHOO_REDIRECT_PATH}"

    class Config:
        env_file = ".env"


settings = Settings()
