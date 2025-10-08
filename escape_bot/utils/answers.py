"""Answer normalization and matching utilities."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

from rapidfuzz.distance import Levenshtein

_whitespace_re = re.compile(r"\s+")
_alnum_re = re.compile(r"[^\w\s]")


def normalize_answer(answer: str) -> str:
    """Normalize an answer by case-folding and collapsing whitespace."""

    normalized = answer.casefold().strip()
    normalized = _whitespace_re.sub(" ", normalized)
    return normalized


def sanitize_for_hash(answer: str) -> str:
    """Produce a consistent sanitized string for hashing answers."""

    return _alnum_re.sub("", normalize_answer(answer))


def hash_answer(answer: str) -> str:
    """Return a SHA256 hash of an answer for audit logging."""

    sanitized = sanitize_for_hash(answer)
    return hashlib.sha256(sanitized.encode("utf-8")).hexdigest()


def is_answer_correct(user_answer: str, accepted_answers: Iterable[str]) -> bool:
    """Check whether a user's answer matches any accepted answer."""

    normalized_user = normalize_answer(user_answer)
    for accepted in accepted_answers:
        normalized_target = normalize_answer(accepted)
        if normalized_user == normalized_target:
            return True
        distance = Levenshtein.distance(normalized_user, normalized_target)
        if len(normalized_target) > 4 and distance <= 1:
            return True
    return False


__all__ = [
    "normalize_answer",
    "hash_answer",
    "is_answer_correct",
]
