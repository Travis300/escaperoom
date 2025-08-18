from __future__ import annotations

"""Yahoo Fantasy API client utilities."""

import asyncio
import time
from typing import Any, Dict

import httpx
from authlib.integrations.httpx_client import OAuth2Client
import yahoo_fantasy_api as yfa

from config import settings
from db import Database


class TokenStore:
    """Persist and retrieve user tokens using :class:`Database`."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_user_token(self, discord_user_id: str) -> Dict[str, Any] | None:
        return await self.db.get_user_token(discord_user_id)

    async def upsert_user_token(self, discord_user_id: str, token: Dict[str, Any]) -> None:
        await self.db.upsert_user_token(discord_user_id, token)


class YahooAuth(httpx.Auth):
    """httpx authentication handler that injects Yahoo OAuth tokens."""

    requires_request_body = False

    def __init__(self, token_store: TokenStore, discord_user_id: str) -> None:
        self.token_store = token_store
        self.discord_user_id = discord_user_id

    def auth_flow(self, request: httpx.Request) -> httpx.Request:
        token = asyncio.run(self._ensure_token())
        request.headers["Authorization"] = f"Bearer {token['access_token']}"
        yield request

    async def _ensure_token(self) -> Dict[str, Any]:
        token = await self.token_store.get_user_token(self.discord_user_id)
        if not token:
            raise RuntimeError("User is not linked with Yahoo.")
        if token["expires_at"] - 60 > time.time():
            return token
        # Refresh token
        client = OAuth2Client(
            settings.YAHOO_CLIENT_ID,
            settings.YAHOO_CLIENT_SECRET,
            token=token,
            redirect_uri=settings.redirect_uri,
        )
        new_token = await client.refresh_token(
            "https://api.login.yahoo.com/oauth2/get_token",
            refresh_token=token["refresh_token"],
        )
        refreshed = {
            "yahoo_guid": token["yahoo_guid"],
            "access_token": new_token["access_token"],
            "refresh_token": new_token.get("refresh_token", token["refresh_token"]),
            "expires_at": int(time.time()) + int(new_token.get("expires_in", 3600)),
            "scope": new_token.get("scope", token.get("scope", "")),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        await self.token_store.upsert_user_token(self.discord_user_id, refreshed)
        return refreshed


class YfaOAuthShim:
    """Minimal object exposing a ``requests``-like interface for yfa."""

    def __init__(self, auth: YahooAuth) -> None:
        self._client = httpx.Client(auth=auth, timeout=20.0)

    # requests-style methods -------------------------------------------------
    def get(self, url: str, params: Dict[str, Any] | None = None, **kw: Any) -> httpx.Response:
        return self._client.get(url, params=params, **kw)

    def post(self, url: str, data: Any = None, json: Any = None, **kw: Any) -> httpx.Response:
        return self._client.post(url, data=data, json=json, **kw)

    def close(self) -> None:
        self._client.close()

    # Compatibility hooks for yahoo_fantasy_api ------------------------------
    @property
    def session(self) -> "YfaOAuthShim":
        return self

    def token_is_valid(self) -> bool:  # pragma: no cover - required by yfa
        return True

    def refresh_access_token(self) -> None:  # pragma: no cover - handled automatically
        return None


def _build_oauth(discord_user_id: str, store: TokenStore) -> YfaOAuthShim:
    auth = YahooAuth(store, discord_user_id)
    return YfaOAuthShim(auth)


def get_game(discord_user_id: str, store: TokenStore, sport: str = "nfl") -> yfa.Game:
    """Return a :class:`yahoo_fantasy_api.Game` for ``discord_user_id``."""
    oauth = _build_oauth(discord_user_id, store)
    return yfa.Game(oauth, sport)


def get_league(discord_user_id: str, league_key: str, store: TokenStore) -> yfa.League:
    """Return a :class:`yahoo_fantasy_api.League` bound to ``discord_user_id``."""
    oauth = _build_oauth(discord_user_id, store)
    return yfa.League(oauth, league_key)
