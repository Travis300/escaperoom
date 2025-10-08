"""Database models and helpers for the escape room bot."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import AsyncIterator, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        Index("idx_players_guild_user", "guild_id", "user_id", unique=True),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow)
    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    wrong_attempts: Mapped[int] = mapped_column(Integer, default=0)


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (
        Index("idx_progress_guild_user", "guild_id", "user_id", unique=True),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    current_level: Mapped[int] = mapped_column(Integer, default=1)
    last_level_update: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow)
    level_started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow)
    next_hint_unlock_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hints_revealed: Mapped[int] = mapped_column(Integer, default=0)
    channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        Index("idx_attempts_lookup", "guild_id", "user_id", "level_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    level_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow)
    is_correct: Mapped[bool] = mapped_column(Integer, default=0)
    answer_hash: Mapped[str] = mapped_column(String(128), default="")


class GuildSettings(Base):
    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hint_interval_minutes: Mapped[int] = mapped_column(Integer, default=10)
    dm_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    lobby_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


class Database:
    """Async database helper providing sessions and setup."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.engine: AsyncEngine = create_async_engine(
            f"sqlite+aiosqlite:///{path}", echo=False, future=True
        )
        self._sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def setup(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            yield session

    async def get_player(self, session: AsyncSession, guild_id: int, user_id: int) -> Optional[Player]:
        stmt = select(Player).where(Player.guild_id == guild_id, Player.user_id == user_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_progress(self, session: AsyncSession, guild_id: int, user_id: int) -> Optional[Progress]:
        stmt = select(Progress).where(Progress.guild_id == guild_id, Progress.user_id == user_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_guild_settings(self, session: AsyncSession, guild_id: int) -> Optional[GuildSettings]:
        stmt = select(GuildSettings).where(GuildSettings.guild_id == guild_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def upsert_guild_settings(
        self,
        session: AsyncSession,
        guild_id: int,
        *,
        hint_interval_minutes: Optional[int] = None,
        dm_mode: Optional[bool] = None,
        lobby_channel_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> GuildSettings:
        settings = await self.get_guild_settings(session, guild_id)
        if settings is None:
            settings = GuildSettings(
                guild_id=guild_id,
                hint_interval_minutes=hint_interval_minutes or 10,
                dm_mode=True if dm_mode is None else dm_mode,
                lobby_channel_id=lobby_channel_id,
                category_id=category_id,
            )
            session.add(settings)
            await session.flush()
        else:
            if hint_interval_minutes is not None:
                settings.hint_interval_minutes = hint_interval_minutes
            if dm_mode is not None:
                settings.dm_mode = dm_mode
            if lobby_channel_id is not None:
                settings.lobby_channel_id = lobby_channel_id
            if category_id is not None:
                settings.category_id = category_id
        return settings

    async def reset_player(self, session: AsyncSession, guild_id: int, user_id: int) -> None:
        await session.execute(
            delete(Attempt).where(
                Attempt.guild_id == guild_id,
                Attempt.user_id == user_id,
            )
        )
        progress = await self.get_progress(session, guild_id, user_id)
        if progress is not None:
            await session.delete(progress)
        player = await self.get_player(session, guild_id, user_id)
        if player is not None:
            await session.delete(player)


__all__ = [
    "Database",
    "Player",
    "Progress",
    "Attempt",
    "GuildSettings",
]
