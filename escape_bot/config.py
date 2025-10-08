"""Configuration and level loading utilities."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, validator

load_dotenv()

LOGGER = logging.getLogger(__name__)


class PromptEmbedModel(BaseModel):
    """Model describing optional embed overrides for a level."""

    title: str = Field(..., description="Embed title for the level prompt.")
    description: str = Field(..., description="Embed description for the level prompt.")
    footer: Optional[str] = Field(None, description="Embed footer text.")


class LevelModel(BaseModel):
    """Model describing a level entry in the YAML file."""

    id: int
    title: str
    description: str
    prompt_embed: Optional[PromptEmbedModel] = None
    answers: List[str] = Field(..., min_items=1)
    hidden_clues: List[str] = Field(default_factory=list, min_items=1)
    timed_hints: List[str] = Field(default_factory=list, min_items=1)
    forward_seeds: List[str] = Field(default_factory=list)

    @validator("answers", "hidden_clues", "timed_hints", each_item=True)
    def strip_strings(cls, value: str) -> str:  # type: ignore[override]
        if not value:
            raise ValueError("entries must not be empty")
        return value.strip()


class SettingsModel(BaseModel):
    """Global settings found in the levels YAML."""

    hint_interval_minutes: int = Field(10, ge=1, le=120)
    dm_mode: bool = Field(True)


class LevelsFileModel(BaseModel):
    """Root model for the YAML file."""

    settings: SettingsModel = Field(default_factory=SettingsModel)
    levels: List[LevelModel] = Field(..., min_items=1)

    @validator("levels")
    def ensure_unique_ids(cls, levels: List[LevelModel]) -> List[LevelModel]:
        ids = {lvl.id for lvl in levels}
        if len(ids) != len(levels):
            raise ValueError("Level IDs must be unique.")
        return sorted(levels, key=lambda lvl: lvl.id)


@dataclass(slots=True)
class BotSettings:
    """Runtime settings loaded from environment variables."""

    token: str
    log_level: str = "INFO"
    database_path: Path = Path("escape.db")
    levels_path: Path = Path("levels.yaml")


def load_bot_settings() -> BotSettings:
    """Load bot runtime settings from environment variables."""

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Create a .env file or set the environment variable.")

    log_level = os.environ.get("LOG_LEVEL", "INFO")
    db_path = Path(os.environ.get("ESCAPE_DB", "escape.db"))
    levels_path = Path(os.environ.get("LEVELS_FILE", "levels.yaml"))

    return BotSettings(
        token=token,
        log_level=log_level,
        database_path=db_path,
        levels_path=levels_path,
    )


def load_levels(path: Path) -> LevelsFileModel:
    """Load and validate levels from the provided YAML path."""

    if not path.exists():
        raise FileNotFoundError(f"Levels file not found at {path}.")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    try:
        levels_file = LevelsFileModel.parse_obj(raw)
    except ValidationError as exc:
        LOGGER.error("Failed to load levels.yaml: %s", exc)
        raise

    level_count = len(levels_file.levels)
    if level_count < 10:
        raise ValueError("levels.yaml must contain at least 10 levels for the escape room.")

    LOGGER.info("Loaded %s levels from %s", level_count, path)
    return levels_file
