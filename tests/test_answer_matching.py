"""Tests for answer normalization and fuzzy matching."""

import pytest

pytest.importorskip("rapidfuzz")

from escape_bot.utils.answers import hash_answer, is_answer_correct, normalize_answer


def test_normalize_answer_collapses_whitespace():
    assert normalize_answer("  HeLLo   World  ") == "hello world"


def test_exact_answer_match():
    assert is_answer_correct("hello", ["hello"])


def test_fuzzy_answer_match_allows_small_typos():
    assert is_answer_correct("helo", ["hello"])
    assert not is_answer_correct("hel", ["hello"])


def test_hash_is_case_insensitive():
    assert hash_answer("Hello") == hash_answer("hello")
