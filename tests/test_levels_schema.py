"""Tests for levels.yaml schema integrity."""
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("pydantic")

from escape_bot.config import load_levels


@pytest.fixture(scope="module")
def levels_config():
    return load_levels(Path("levels.yaml"))


def test_levels_count(levels_config):
    assert len(levels_config.levels) >= 10


def test_levels_have_required_fields(levels_config):
    for level in levels_config.levels:
        assert level.answers, "Level must have answers"
        assert 2 <= len(level.hidden_clues) <= 4
        assert 2 <= len(level.timed_hints) <= 3
        if level.forward_seeds:
            assert all(isinstance(seed, str) for seed in level.forward_seeds)


def test_settings_loaded(levels_config):
    assert levels_config.settings.hint_interval_minutes >= 1
    assert isinstance(levels_config.settings.dm_mode, bool)
