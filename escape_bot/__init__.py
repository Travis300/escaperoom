"""Escape Room Discord bot package."""

__all__ = ["EscapeBot"]


def __getattr__(name: str):
    if name == "EscapeBot":
        from .bot import EscapeBot

        return EscapeBot
    raise AttributeError(name)
