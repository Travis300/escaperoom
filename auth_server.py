from __future__ import annotations

"""FastAPI application handling Yahoo OAuth2 callbacks."""

import secrets
import time
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client

from config import settings
from db import Database
from utils import setup_logger

app = FastAPI()
logger = setup_logger()
db = Database()


@app.on_event("startup")
async def startup() -> None:
    await db.connect()


@app.on_event("shutdown")
async def shutdown() -> None:
    await db.close()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/auth/start")
async def auth_start(discord_user_id: str = Query(..., description="Discord user snowflake")) -> RedirectResponse:
    if not discord_user_id.isdigit():
        raise HTTPException(400, "invalid discord_user_id")
    state = secrets.token_urlsafe(16)
    await db.add_pending_oauth(state, discord_user_id)
    params = {
        "response_type": "code",
        "client_id": settings.YAHOO_CLIENT_ID,
        "redirect_uri": settings.redirect_uri,
        "scope": "fspt-r fspt-w",
        "state": state,
    }
    url = httpx.URL("https://api.login.yahoo.com/oauth2/request_auth").include_query_params(**params)
    return RedirectResponse(str(url))


@app.get("/auth/callback")
async def auth_callback(code: str, state: str) -> HTMLResponse:
    pending = await db.pop_pending_oauth(state)
    if not pending:
        raise HTTPException(400, "invalid state")
    discord_user_id = pending["discord_user_id"]
    client = AsyncOAuth2Client(
        settings.YAHOO_CLIENT_ID,
        settings.YAHOO_CLIENT_SECRET,
        redirect_uri=settings.redirect_uri,
    )
    token = await client.fetch_token(
        "https://api.login.yahoo.com/oauth2/get_token",
        code=code,
        grant_type="authorization_code",
    )
    resp = await client.get("https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1?format=json")
    resp.raise_for_status()
    user = resp.json()["fantasy_content"]["users"]["0"]["user"][0]
    yahoo_guid = user["guid"]
    data = {
        "yahoo_guid": yahoo_guid,
        "access_token": token["access_token"],
        "refresh_token": token["refresh_token"],
        "expires_at": int(time.time()) + int(token.get("expires_in", 3600)),
        "scope": token.get("scope", ""),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    await db.upsert_user_token(discord_user_id, data)
    html = "<h1>Yahoo linked!</h1><p>You may return to Discord.</p>"
    return HTMLResponse(html)
