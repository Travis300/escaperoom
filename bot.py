"""Entrypoint for running the escape room bot."""
from __future__ import annotations

import asyncio
import logging

from escape_bot.bot import create_bot


async def main() -> None:
    bot = await create_bot()
    try:
        await bot.start(bot.settings.token)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Shutdown requested by keyboard interrupt.")
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
