from __future__ import annotations

"""Miscellaneous helpers."""

import logging
from typing import Iterable, List


def setup_logger() -> logging.Logger:
    """Configure and return a module-level logger."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return logging.getLogger("yahoo_bot")


def clean(text: str, limit: int = 1900) -> str:
    """Collapse whitespace and truncate messages for Discord."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def paginate(lines: Iterable[str], size: int = 15) -> List[str]:
    """Split an iterable of lines into chunks of ``size``."""
    chunk, pages = [], []
    for line in lines:
        chunk.append(line)
        if len(chunk) == size:
            pages.append("\n".join(chunk))
            chunk = []
    if chunk:
        pages.append("\n".join(chunk))
    return pages
