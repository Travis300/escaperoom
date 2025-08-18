from __future__ import annotations

"""Discord bot providing Yahoo Fantasy Football commands."""

import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands

from config import settings
from db import Database
from utils import clean, setup_logger
from yahoo_client import TokenStore, get_game, get_league

logger = setup_logger()


def _to_thread(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, lambda: fn(*args, **kwargs))


class FantasyBot(discord.Client):
    """Discord client holding the command tree and database handle."""

    def __init__(self, db: Database) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.db = db
        self.store = TokenStore(db)

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.tree.sync()
        logger.info("Bot ready")


bot = FantasyBot(Database())


@bot.tree.command(name="link_yahoo", description="Link your Yahoo account")
async def link_yahoo(interaction: discord.Interaction) -> None:
    url = f"{settings.AUTH_BASE_URL.rstrip('/')}/auth/start?discord_user_id={interaction.user.id}"
    await interaction.response.send_message(
        f"Click here to link your Yahoo account: {url}", ephemeral=True
    )


@bot.tree.command(name="pick_league", description="List your Yahoo leagues")
async def pick_league(interaction: discord.Interaction) -> None:
    try:
        game = get_game(str(interaction.user.id), store=bot.store)
        leagues = await _to_thread(game.league_ids)
    except Exception as exc:  # noqa: BLE001
        logger.exception("league_ids failed: %s", exc)
        await interaction.response.send_message("Failed to fetch leagues. Did you link?", ephemeral=True)
        return
    if not leagues:
        await interaction.response.send_message("No leagues found.", ephemeral=True)
        return
    lines = [f"{i+1}. {key}" for i, key in enumerate(leagues[:10])]
    msg = clean("\n".join(lines) + "\nUse /set_league_key <key> to select one")
    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="set_league_key", description="Set the league for this server")
@app_commands.describe(league_key="Yahoo league key")
async def set_league_key(interaction: discord.Interaction, league_key: str) -> None:
    try:
        league = get_league(str(interaction.user.id), league_key, store=bot.store)
        current_week = await _to_thread(league.current_week)
    except Exception as exc:  # noqa: BLE001
        logger.exception("set_league failed: %s", exc)
        await interaction.response.send_message("Could not validate league key.", ephemeral=True)
        return
    assert interaction.guild is not None
    await bot.db.set_guild_setting(interaction.guild.id, league_key, str(interaction.user.id))
    await interaction.response.send_message(
        f"League set to {league_key}. Current week: {current_week}", ephemeral=True
    )


@bot.tree.command(name="standings", description="Show league standings")
async def standings(interaction: discord.Interaction) -> None:
    assert interaction.guild is not None
    league_key = await bot.db.get_guild_setting(interaction.guild.id)
    if not league_key:
        await interaction.response.send_message("No league configured. Run /pick_league then /set_league_key.")
        return
    try:
        league = get_league(str(interaction.user.id), league_key, store=bot.store)
        standings = await _to_thread(league.standings)
        current_week = await _to_thread(league.current_week)
    except Exception as exc:  # noqa: BLE001
        logger.exception("standings failed: %s", exc)
        await interaction.response.send_message("Failed to fetch standings. Is your account linked?", ephemeral=True)
        return
    lines = []
    for team in sorted(standings, key=lambda t: t["rank"]):
        record = f"{team['name']} — {team['wins']}-{team['losses']}"
        if team.get("ties"):
            record += f"-{team['ties']}"
        record += f" ({float(team['percentage']):.3f})"
        lines.append(record)
    msg = clean("\n".join(lines))
    await interaction.response.send_message(f"Week {current_week} standings:\n{msg}")


@bot.tree.command(name="matchups", description="Show weekly matchups")
@app_commands.describe(week="Week number; defaults to current")
async def matchups(interaction: discord.Interaction, week: Optional[int] = None) -> None:
    assert interaction.guild is not None
    league_key = await bot.db.get_guild_setting(interaction.guild.id)
    if not league_key:
        await interaction.response.send_message("No league configured. Run /pick_league then /set_league_key.")
        return
    try:
        league = get_league(str(interaction.user.id), league_key, store=bot.store)
        if week is None:
            week = await _to_thread(league.current_week)
        data = await _to_thread(league.matchups, week)
    except Exception as exc:  # noqa: BLE001
        logger.exception("matchups failed: %s", exc)
        await interaction.response.send_message("Failed to fetch matchups.", ephemeral=True)
        return
    lines = []
    for m in data:
        a = m["team1_name"]
        b = m["team2_name"] or "BYE"
        pts1 = m.get("team1_points", 0)
        pts2 = m.get("team2_points", 0)
        lines.append(f"{a} ({pts1}) vs {b} ({pts2})")
    msg = clean("\n".join(lines))
    await interaction.response.send_message(f"Week {week} matchups:\n{msg}")


@bot.tree.command(name="roster", description="Show a team roster")
@app_commands.describe(team_name="Partial team name")
async def roster(interaction: discord.Interaction, team_name: str) -> None:
    assert interaction.guild is not None
    league_key = await bot.db.get_guild_setting(interaction.guild.id)
    if not league_key:
        await interaction.response.send_message("No league configured. Run /pick_league then /set_league_key.")
        return
    try:
        league = get_league(str(interaction.user.id), league_key, store=bot.store)
        standings = await _to_thread(league.standings)
    except Exception as exc:  # noqa: BLE001
        logger.exception("roster standings failed: %s", exc)
        await interaction.response.send_message("Failed to fetch teams.", ephemeral=True)
        return
    team_key = None
    for team in standings:
        if team_name.lower() in team["name"].lower():
            team_key = team["team_key"]
            break
    if not team_key:
        await interaction.response.send_message("Team not found.", ephemeral=True)
        return
    try:
        roster_data = await _to_thread(league.roster, team_key)
    except Exception as exc:  # noqa: BLE001
        logger.exception("roster fetch failed: %s", exc)
        await interaction.response.send_message("Failed to fetch roster.", ephemeral=True)
        return
    players = [p["name"] for p in roster_data]
    msg = clean("\n".join(players))
    await interaction.response.send_message(f"Roster for {team_name}:\n{msg}")


@bot.tree.command(name="unlink_yahoo", description="Remove stored Yahoo tokens")
async def unlink_yahoo(interaction: discord.Interaction) -> None:
    await bot.db.delete_user_token(str(interaction.user.id))
    await interaction.response.send_message("Yahoo account unlinked.", ephemeral=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot.run(settings.DISCORD_TOKEN)
