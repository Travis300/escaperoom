"""Discord bot entry point and configuration wiring."""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import BotSettings, LevelsFileModel, load_bot_settings, load_levels
from .database import Database

LOGGER = logging.getLogger(__name__)


class EscapeBot(commands.Bot):
    """Custom bot instance with preloaded configuration and database."""

    def __init__(self, settings: BotSettings, levels: LevelsFileModel, database: Database) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.levels_config = levels
        self.database = database
        self.logger = LOGGER

    async def setup_hook(self) -> None:
        await self.database.setup()
        from .cogs.escape import EscapeCog

        await self.add_cog(EscapeCog(self))
        self.logger.info("EscapeCog loaded and ready.")


async def create_bot() -> EscapeBot:
    """Factory for creating and configuring the bot instance."""

    settings = load_bot_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    levels = load_levels(settings.levels_path)
    database = Database(settings.database_path)
    bot = EscapeBot(settings, levels, database)
    return bot


__all__ = ["EscapeBot", "create_bot"]
