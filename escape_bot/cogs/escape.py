"""Escape room command handlers."""
from __future__ import annotations

import datetime as dt
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from ..config import LevelModel, LevelsFileModel
from ..database import Attempt, Database, GuildSettings, Player, Progress
from ..utils.answers import hash_answer, is_answer_correct
from ..utils.embeds import (
    BRAND_COLOR,
    create_completion_embed,
    create_hint_embed,
    create_leaderboard_embed,
    create_level_embed,
)

ANSWER_RATE_SECONDS = 3


class EscapeCog(commands.GroupCog, name="escape"):
    """Primary command group for the escape room."""

    config = app_commands.Group(name="config", description="Configure escape room settings.")

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(group_name="escape", group_description="Experience a net-runner escape room.")
        self.bot = bot
        assert isinstance(bot, commands.Bot)
        self.levels_config: LevelsFileModel = bot.levels_config  # type: ignore[attr-defined]
        self.database: Database = bot.database  # type: ignore[attr-defined]
        self._levels = {level.id: level for level in self.levels_config.levels}
        self._answer_rate: Dict[tuple[int, int], dt.datetime] = {}

    # Utility helpers -------------------------------------------------

    async def get_guild_settings(self, guild_id: int) -> GuildSettings:
        async for session in self.database.session():
            settings = await self.database.get_guild_settings(session, guild_id)
            if settings is None:
                defaults = self.levels_config.settings
                settings = await self.database.upsert_guild_settings(
                    session,
                    guild_id,
                    hint_interval_minutes=defaults.hint_interval_minutes,
                    dm_mode=defaults.dm_mode,
                )
                await session.commit()
            else:
                await session.flush()
            return settings
        raise RuntimeError("Database session closed unexpectedly")

    async def ensure_lobby_thread(
        self,
        interaction: discord.Interaction,
        settings: GuildSettings,
        member: discord.abc.User,
    ) -> tuple[discord.abc.MessageableChannel, str]:
        assert interaction.guild is not None
        guild = interaction.guild
        lobby_channel: Optional[discord.TextChannel] = None

        if settings.lobby_channel_id:
            lobby_channel = guild.get_channel(settings.lobby_channel_id)  # type: ignore[assignment]
            if not isinstance(lobby_channel, discord.TextChannel):
                lobby_channel = None

        if lobby_channel is None:
            category = None
            if settings.category_id:
                maybe_category = guild.get_channel(settings.category_id)
                if isinstance(maybe_category, discord.CategoryChannel):
                    category = maybe_category
            if category is None:
                category = await guild.create_category("Escape Room")
            lobby_channel = await category.create_text_channel("lobby", reason="Escape room setup")
            async for session in self.database.session():
                await self.database.upsert_guild_settings(
                    session,
                    guild_id=guild.id,
                    lobby_channel_id=lobby_channel.id,
                    category_id=category.id,
                )
                await session.commit()
                break

        thread = await lobby_channel.create_thread(
            name=f"escape-{interaction.user.display_name}",
            type=discord.ChannelType.private_thread,
            invitable=False,
        )
        await thread.add_user(member)
        return thread, "private thread"

    async def get_level(self, level_id: int) -> LevelModel:
        try:
            return self._levels[level_id]
        except KeyError as exc:
            raise ValueError(f"Level {level_id} is not defined.") from exc

    def _check_rate_limit(self, guild_id: int, user_id: int) -> bool:
        now = dt.datetime.utcnow()
        key = (guild_id, user_id)
        last = self._answer_rate.get(key)
        if last and (now - last).total_seconds() < ANSWER_RATE_SECONDS:
            return False
        self._answer_rate[key] = now
        return True

    async def _get_player_state(self, guild_id: int, user_id: int) -> tuple[Player, Progress]:
        async for session in self.database.session():
            player = await self.database.get_player(session, guild_id, user_id)
            progress = await self.database.get_progress(session, guild_id, user_id)
            if player is None or progress is None:
                raise LookupError("Player has not started the escape room yet.")
            session.expunge_all()
            return player, progress
        raise RuntimeError("Failed to acquire player state")

    async def _record_attempt(
        self,
        session,
        guild_id: int,
        user_id: int,
        level_id: int,
        *,
        is_correct: bool,
        answer_text: str,
    ) -> None:
        attempt = Attempt(
            guild_id=guild_id,
            user_id=user_id,
            level_id=level_id,
            is_correct=is_correct,
            answer_hash=hash_answer(answer_text),
        )
        session.add(attempt)

    # Slash commands --------------------------------------------------

    async def resolve_destination(
        self,
        interaction: discord.Interaction,
        progress: Progress,
        settings: GuildSettings,
        member: Optional[discord.abc.User] = None,
    ) -> tuple[discord.abc.MessageableChannel, str]:
        assert interaction.guild is not None
        user = member or interaction.user
        if settings.dm_mode:
            dm = user.dm_channel or await user.create_dm()
            progress.channel_id = dm.id
            return dm, "direct messages"

        # Attempt to reuse an existing thread
        channel = None
        if progress.channel_id:
            channel = interaction.guild.get_channel(progress.channel_id)  # type: ignore[assignment]
            if channel is None:
                channel = interaction.guild.get_thread(progress.channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(progress.channel_id)
                except Exception:  # pragma: no cover - network dependent
                    channel = None
        if isinstance(channel, discord.Thread):
            if channel.archived:
                await channel.edit(archived=False)
            await channel.add_user(user)
            return channel, "private thread"

        destination, desc = await self.ensure_lobby_thread(interaction, settings, user)
        progress.channel_id = destination.id
        return destination, desc

    @app_commands.command(name="start", description="Enter the escape room.")
    @app_commands.guild_only()
    async def start(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        settings = await self.get_guild_settings(interaction.guild.id)
        async for session in self.database.session():
            progress = await self.database.get_progress(session, interaction.guild.id, interaction.user.id)
            now = dt.datetime.utcnow()
            if progress is None:
                player = await self.database.get_player(session, interaction.guild.id, interaction.user.id)
                if player is None:
                    player = Player(
                        guild_id=interaction.guild.id,
                        user_id=interaction.user.id,
                        started_at=now,
                    )
                    session.add(player)
                progress = Progress(
                    guild_id=interaction.guild.id,
                    user_id=interaction.user.id,
                    current_level=1,
                    level_started_at=now,
                    last_level_update=now,
                    hints_revealed=0,
                    next_hint_unlock_at=now + dt.timedelta(minutes=settings.hint_interval_minutes),
                )
                session.add(progress)
                await session.commit()
            else:
                await session.flush()
            session.expunge(progress)
            break

        destination, channel_desc = await self.resolve_destination(interaction, progress, settings, interaction.user)
        async for session in self.database.session():
            db_progress = await self.database.get_progress(session, interaction.guild.id, interaction.user.id)
            if db_progress:
                db_progress.channel_id = progress.channel_id
                session.add(db_progress)
                await session.commit()
            break

        level = await self.get_level(progress.current_level)
        embed = create_level_embed(level, progress, len(self._levels), progress.hints_revealed)
        await destination.send(embed=embed)
        await interaction.response.send_message(
            f"You're in! Check your {channel_desc} for the first level.", ephemeral=True
        )

    @app_commands.command(name="level", description="Show your current level information.")
    @app_commands.guild_only()
    async def level(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        try:
            _, progress = await self._get_player_state(interaction.guild.id, interaction.user.id)
        except LookupError:
            await interaction.response.send_message("Use /escape start to begin your run.", ephemeral=True)
            return
        level = await self.get_level(progress.current_level)
        embed = create_level_embed(level, progress, len(self._levels), progress.hints_revealed)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="answer", description="Submit an answer for your current level.")
    @app_commands.describe(text="Your solution to the level.")
    @app_commands.guild_only()
    async def answer(self, interaction: discord.Interaction, text: str) -> None:
        assert interaction.guild is not None
        if not self._check_rate_limit(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message(
                "Hold up—give the neural net a moment before another guess.",
                ephemeral=True,
            )
            return

        try:
            player, progress = await self._get_player_state(interaction.guild.id, interaction.user.id)
        except LookupError:
            await interaction.response.send_message("Use /escape start to get access first.", ephemeral=True)
            return

        level = await self.get_level(progress.current_level)
        correct = is_answer_correct(text, level.answers)
        async for session in self.database.session():
            db_progress = await self.database.get_progress(session, interaction.guild.id, interaction.user.id)
            db_player = await self.database.get_player(session, interaction.guild.id, interaction.user.id)
            assert db_progress and db_player
            await self._record_attempt(
                session,
                interaction.guild.id,
                interaction.user.id,
                level.id,
                is_correct=correct,
                answer_text=text,
            )
            now = dt.datetime.utcnow()
            if correct:
                settings = await self.get_guild_settings(interaction.guild.id)
                destination, _ = await self.resolve_destination(
                    interaction, db_progress, settings, interaction.user
                )
                if level.id >= len(self._levels):
                    db_player.completed_at = now
                    total_time = now - db_player.started_at
                    embed = create_completion_embed(total_time, db_player.hints_used, db_player.wrong_attempts)
                    session.add(db_player)
                    await session.commit()
                    await destination.send(embed=embed)
                    await interaction.response.send_message(
                        "Legendary. You've pierced every firewall.",
                        ephemeral=True,
                    )
                    return
                next_level_id = level.id + 1
                next_level = await self.get_level(next_level_id)
                db_progress.current_level = next_level_id
                db_progress.last_level_update = now
                db_progress.level_started_at = now
                db_progress.hints_revealed = 0
                db_progress.next_hint_unlock_at = now + dt.timedelta(minutes=settings.hint_interval_minutes)
                session.add(db_progress)
                await session.commit()
                embed = create_level_embed(next_level, db_progress, len(self._levels), 0)
                await destination.send(embed=embed)
                await interaction.response.send_message(
                    "Jackpot! Check your escape channel for the next drop.",
                    ephemeral=True,
                )
                return
            else:
                db_player.wrong_attempts += 1
                if db_progress.next_hint_unlock_at is None:
                    settings = await self.get_guild_settings(interaction.guild.id)
                    db_progress.next_hint_unlock_at = now + dt.timedelta(minutes=settings.hint_interval_minutes)
                session.add(db_player)
                session.add(db_progress)
                await session.commit()
                remaining = db_progress.next_hint_unlock_at - now if db_progress.next_hint_unlock_at else dt.timedelta(0)
                remaining_text = str(remaining).split(".")[0] if remaining.total_seconds() > 0 else "available now"
                await interaction.response.send_message(
                    f"Not quite. Next hint unlocks in {remaining_text}.",
                    ephemeral=True,
                )
                return

    @app_commands.command(name="hint", description="Reveal the next available hint.")
    @app_commands.guild_only()
    async def hint(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        try:
            player, progress = await self._get_player_state(interaction.guild.id, interaction.user.id)
        except LookupError:
            await interaction.response.send_message("Start first with /escape start.", ephemeral=True)
            return
        level = await self.get_level(progress.current_level)
        now = dt.datetime.utcnow()
        if progress.hints_revealed >= len(level.timed_hints):
            await interaction.response.send_message("You've seen all hints for this level.", ephemeral=True)
            return
        unlock_at = progress.next_hint_unlock_at or progress.level_started_at
        if now < unlock_at:
            remaining = unlock_at - now
            await interaction.response.send_message(
                f"Decrypt patience... next hint in {str(remaining).split('.')[0]}",
                ephemeral=True,
            )
            return

        next_hint = level.timed_hints[progress.hints_revealed]
        progress.hints_revealed += 1
        player.hints_used += 1
        if progress.hints_revealed >= len(level.timed_hints):
            progress.next_hint_unlock_at = None
            remaining = None
        else:
            settings = await self.get_guild_settings(interaction.guild.id)
            progress.next_hint_unlock_at = now + dt.timedelta(minutes=settings.hint_interval_minutes)
            remaining = progress.next_hint_unlock_at - now

        async for session in self.database.session():
            db_progress = await self.database.get_progress(session, interaction.guild.id, interaction.user.id)
            db_player = await self.database.get_player(session, interaction.guild.id, interaction.user.id)
            assert db_progress and db_player
            db_progress.hints_revealed = progress.hints_revealed
            db_progress.next_hint_unlock_at = progress.next_hint_unlock_at
            db_player.hints_used = player.hints_used
            session.add(db_progress)
            session.add(db_player)
            await session.commit()
            break

        embed = create_hint_embed(level, next_hint, remaining)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="View the fastest net-runners.")
    @app_commands.describe(scope="Scope of the leaderboard: guild or global")
    async def leaderboard(self, interaction: discord.Interaction, scope: Optional[str] = "guild") -> None:
        scope = (scope or "guild").lower()
        rows: list[tuple[Player, float]] = []
        async for session in self.database.session():
            stmt = (
                select(
                    Player,
                    (func.julianday(Player.completed_at) - func.julianday(Player.started_at)).label("duration"),
                )
                .where(Player.completed_at.is_not(None))
                .order_by("duration", Player.hints_used, Player.wrong_attempts)
                .limit(10)
            )
            if scope != "global":
                if interaction.guild is None:
                    await interaction.response.send_message("Guild leaderboard only works in servers.", ephemeral=True)
                    return
                stmt = stmt.where(Player.guild_id == interaction.guild.id)
            result = await session.execute(stmt)
            rows = result.all()
            break

        lines = []
        for idx, (player, duration) in enumerate(rows, start=1):
            if player.completed_at is None:
                continue
            delta = dt.timedelta(days=float(duration))
            user = self.bot.get_user(player.user_id)
            user_name = user.display_name if user else f"<@{player.user_id}>"
            lines.append(
                f"**{idx}.** {user_name} – {str(delta).split('.')[0]}, hints {player.hints_used}, misses {player.wrong_attempts}"
            )
        if not lines:
            lines.append("No runs completed yet. Be the first hacker legend.")
        title = "Global Escape Leaderboard" if scope == "global" else f"Guild Leaderboard"
        embed = create_leaderboard_embed(title, "\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="reset", description="Reset a player's progress (admin only).")
    @app_commands.describe(user="Player to reset; defaults to yourself")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        assert interaction.guild is not None
        target = user or interaction.user
        async for session in self.database.session():
            await self.database.reset_player(session, interaction.guild.id, target.id)
            await session.commit()
            break
        await interaction.response.send_message(
            f"Progress for {target.mention} has been reset.", ephemeral=True
        )

    @app_commands.command(name="skip", description="Advance a player by one level (admin only).")
    @app_commands.describe(user="Player to skip forward; defaults to yourself")
    @app_commands.checks.has_permissions(administrator=True)
    async def skip(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        assert interaction.guild is not None
        target = user or interaction.user
        async for session in self.database.session():
            progress = await self.database.get_progress(session, interaction.guild.id, target.id)
            if progress is None:
                await interaction.response.send_message("Player has not started yet.", ephemeral=True)
                return
            if progress.current_level >= len(self._levels):
                await interaction.response.send_message("Already at or beyond final level.", ephemeral=True)
                return
            settings = await self.get_guild_settings(interaction.guild.id)
            destination, _ = await self.resolve_destination(interaction, progress, settings, target)
            progress.current_level += 1
            progress.level_started_at = dt.datetime.utcnow()
            progress.last_level_update = progress.level_started_at
            progress.hints_revealed = 0
            progress.next_hint_unlock_at = progress.level_started_at + dt.timedelta(
                minutes=settings.hint_interval_minutes
            )
            session.add(progress)
            await session.commit()
            next_level = await self.get_level(progress.current_level)
            embed = create_level_embed(next_level, progress, len(self._levels), 0)
            await destination.send(embed=embed)
            await interaction.response.send_message(
                f"Skipped {target.mention} to level {progress.current_level}.",
                ephemeral=True,
            )
            return

    @app_commands.command(name="status", description="Check a player's status (mods).")
    @app_commands.describe(user="Player to inspect; defaults to yourself")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        assert interaction.guild is not None
        target = user or interaction.user
        try:
            player, progress = await self._get_player_state(interaction.guild.id, target.id)
        except LookupError:
            await interaction.response.send_message("Player has not entered the escape room.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Status for {target.display_name}",
            colour=BRAND_COLOR,
        )
        embed.add_field(name="Level", value=f"{progress.current_level}/{len(self._levels)}", inline=True)
        embed.add_field(name="Hints used", value=str(player.hints_used), inline=True)
        embed.add_field(name="Wrong attempts", value=str(player.wrong_attempts), inline=True)
        elapsed = dt.datetime.utcnow() - progress.level_started_at
        embed.add_field(name="On level for", value=str(elapsed).split(".")[0], inline=False)
        if player.completed_at:
            total = player.completed_at - player.started_at
            embed.add_field(name="Total time", value=str(total).split(".")[0], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config.command(name="show", description="Display current configuration.")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_show(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        settings = await self.get_guild_settings(interaction.guild.id)
        embed = discord.Embed(title="Escape Room Configuration", colour=BRAND_COLOR)
        embed.add_field(name="DM mode", value="Enabled" if settings.dm_mode else "Disabled", inline=True)
        embed.add_field(name="Hint interval", value=f"{settings.hint_interval_minutes} min", inline=True)
        channel_value = "Not set"
        if settings.lobby_channel_id:
            channel_value = f"<#{settings.lobby_channel_id}>"
        embed.add_field(name="Lobby channel", value=channel_value, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config.command(name="set", description="Update configuration values.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        dm_mode="Toggle DM delivery mode.",
        hint_interval="Minutes between hint unlocks (1-120).",
        lobby_channel="Channel used to host private threads.",
    )
    async def config_set(
        self,
        interaction: discord.Interaction,
        dm_mode: Optional[bool] = None,
        hint_interval: Optional[app_commands.Range[int, 1, 120]] = None,
        lobby_channel: Optional[discord.TextChannel] = None,
    ) -> None:
        assert interaction.guild is not None
        if dm_mode is None and hint_interval is None and lobby_channel is None:
            await interaction.response.send_message("No changes provided.", ephemeral=True)
            return

        async for session in self.database.session():
            category_id = None
            lobby_channel_id = lobby_channel.id if lobby_channel else None
            if lobby_channel and lobby_channel.category:
                category_id = lobby_channel.category.id
            await self.database.upsert_guild_settings(
                session,
                interaction.guild.id,
                dm_mode=dm_mode,
                hint_interval_minutes=int(hint_interval) if hint_interval is not None else None,
                lobby_channel_id=lobby_channel_id,
                category_id=category_id,
            )
            await session.commit()
            break

        await interaction.response.send_message("Configuration updated.", ephemeral=True)

    @reset.error
    async def reset_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("Admins only.", ephemeral=True)
        else:
            raise error

    @skip.error
    async def skip_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("Admins only.", ephemeral=True)
        else:
            raise error

    @status.error
    async def status_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("Mods only.", ephemeral=True)
        else:
            raise error

    @config_show.error
    async def config_show_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("Admins only.", ephemeral=True)
        else:
            raise error

    @config_set.error
    async def config_set_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("Admins only.", ephemeral=True)
        else:
            raise error

