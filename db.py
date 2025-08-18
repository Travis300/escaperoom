from __future__ import annotations

"""Asynchronous SQLite database helper."""

import time
from typing import Any, Dict, Optional

import aiosqlite


ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Database:
    """Small wrapper around :mod:`aiosqlite` providing helper methods."""

    def __init__(self, path: str = "bot.db") -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the database and create tables if necessary."""
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._create_tables()

    async def _create_tables(self) -> None:
        assert self._conn
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_tokens (
                discord_user_id TEXT PRIMARY KEY,
                yahoo_guid      TEXT NOT NULL,
                access_token    TEXT NOT NULL,
                refresh_token   TEXT NOT NULL,
                expires_at      INTEGER NOT NULL,
                scope           TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending_oauth (
                state           TEXT PRIMARY KEY,
                discord_user_id TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id        INTEGER PRIMARY KEY,
                league_key      TEXT NOT NULL,
                set_by_user_id  TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            """
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    # Token store ---------------------------------------------------------
    async def get_user_token(self, discord_user_id: str) -> Optional[Dict[str, Any]]:
        """Return token row for ``discord_user_id`` if available."""
        assert self._conn
        cur = await self._conn.execute(
            "SELECT * FROM user_tokens WHERE discord_user_id = ?",
            (discord_user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def upsert_user_token(self, discord_user_id: str, token: Dict[str, Any]) -> None:
        """Insert or update a token row."""
        assert self._conn
        await self._conn.execute(
            """
            INSERT INTO user_tokens (
                discord_user_id, yahoo_guid, access_token, refresh_token,
                expires_at, scope, updated_at
            ) VALUES (
                :discord_user_id, :yahoo_guid, :access_token, :refresh_token,
                :expires_at, :scope, :updated_at
            ) ON CONFLICT(discord_user_id) DO UPDATE SET
                yahoo_guid=excluded.yahoo_guid,
                access_token=excluded.access_token,
                refresh_token=excluded.refresh_token,
                expires_at=excluded.expires_at,
                scope=excluded.scope,
                updated_at=excluded.updated_at
            """,
            {**token, "discord_user_id": discord_user_id},
        )
        await self._conn.commit()

    async def delete_user_token(self, discord_user_id: str) -> None:
        assert self._conn
        await self._conn.execute(
            "DELETE FROM user_tokens WHERE discord_user_id = ?",
            (discord_user_id,),
        )
        await self._conn.commit()

    # Pending OAuth ------------------------------------------------------
    async def add_pending_oauth(self, state: str, discord_user_id: str) -> None:
        assert self._conn
        await self._conn.execute(
            "INSERT INTO pending_oauth(state, discord_user_id, created_at) VALUES(?, ?, ?)",
            (state, discord_user_id, time.strftime(ISO_FORMAT, time.gmtime())),
        )
        await self._conn.commit()

    async def pop_pending_oauth(self, state: str) -> Optional[Dict[str, Any]]:
        assert self._conn
        cur = await self._conn.execute(
            "SELECT * FROM pending_oauth WHERE state = ?",
            (state,),
        )
        row = await cur.fetchone()
        if row:
            await self._conn.execute("DELETE FROM pending_oauth WHERE state = ?", (state,))
            await self._conn.commit()
            return dict(row)
        return None

    # Guild settings -----------------------------------------------------
    async def get_guild_setting(self, guild_id: int) -> Optional[str]:
        assert self._conn
        cur = await self._conn.execute(
            "SELECT league_key FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cur.fetchone()
        return row["league_key"] if row else None

    async def set_guild_setting(self, guild_id: int, league_key: str, set_by_user_id: str) -> None:
        assert self._conn
        await self._conn.execute(
            """
            INSERT INTO guild_settings(guild_id, league_key, set_by_user_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                league_key=excluded.league_key,
                set_by_user_id=excluded.set_by_user_id,
                updated_at=excluded.updated_at
            """,
            (
                guild_id,
                league_key,
                set_by_user_id,
                time.strftime(ISO_FORMAT, time.gmtime()),
            ),
        )
        await self._conn.commit()
