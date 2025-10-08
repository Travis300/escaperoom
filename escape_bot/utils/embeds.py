"""Embed construction helpers."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import discord

from ..config import LevelModel
from ..database import Progress

BRAND_COLOR = 0x5865F2  # Discord blurple


def create_level_embed(
    level: LevelModel,
    progress: Progress,
    total_levels: int,
    hints_unlocked: int,
) -> discord.Embed:
    """Create a rich embed showing the current level state."""

    embed_title = level.prompt_embed.title if level.prompt_embed else f"Level {level.id}: {level.title}"
    description = level.prompt_embed.description if level.prompt_embed else level.description

    embed = discord.Embed(title=embed_title, description=description, colour=BRAND_COLOR)
    embed.add_field(name="Progress", value=f"Level {level.id} / {total_levels}", inline=True)
    embed.add_field(
        name="Hints unlocked",
        value=f"{hints_unlocked}/{len(level.timed_hints)}",
        inline=True,
    )
    elapsed = dt.datetime.utcnow() - progress.level_started_at
    embed.add_field(name="Time on level", value=str(elapsed).split(".")[0], inline=False)

    footer_text = level.prompt_embed.footer if level.prompt_embed and level.prompt_embed.footer else "Trust no log, only your wits."
    embed.set_footer(text=footer_text)
    return embed


def create_completion_embed(total_time: dt.timedelta, hints_used: int, wrong_attempts: int) -> discord.Embed:
    embed = discord.Embed(
        title="Escape Complete!",
        description="You cracked every layer of the net. Respect.",
        colour=BRAND_COLOR,
    )
    embed.add_field(name="Total time", value=str(total_time).split(".")[0], inline=False)
    embed.add_field(name="Hints used", value=str(hints_used), inline=True)
    embed.add_field(name="Wrong attempts", value=str(wrong_attempts), inline=True)
    embed.set_footer(text="Share your glory, but never the answers.")
    return embed


def create_hint_embed(level: LevelModel, hint_text: str, remaining: Optional[dt.timedelta]) -> discord.Embed:
    embed = discord.Embed(
        title=f"Hint for Level {level.id}",
        description=hint_text,
        colour=BRAND_COLOR,
    )
    if remaining is not None and remaining.total_seconds() > 0:
        embed.set_footer(text=f"Next hint unlocks in {str(remaining).split('.')[0]}")
    return embed


def create_leaderboard_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, colour=BRAND_COLOR)
    embed.set_footer(text="Times are from first level view to completion.")
    return embed

