# Escape Room Discord Bot

A production-ready Discord escape-room experience built with `discord.py` 2.x and Python 3.11. Players tackle ten escalating internet-themed puzzles, uncovering hidden clues, timed hints, and forward seeds that link each level together. Progress is persisted per server in SQLite with async SQLAlchemy, and gameplay content lives in `levels.yaml` for easy iteration.

## Features
- ✅ Slash-command driven gameplay (`/escape …`) with embeds and ephemeral responses.
- ✅ Ten handcrafted levels with hidden clues, timed hints, and forward seeds.
- ✅ Timed hint unlocks per player, rate-limited answer submissions, and anti-cheat nudges.
- ✅ Persistent progress tracking, attempts history, and leaderboards (guild + global).
- ✅ Optional DM or private-thread delivery per guild, configurable via `/escape config`.
- ✅ YAML-driven content with schema validation and unit tests.

## Downloading the Project

You can obtain the bot source in two common ways:

1. **Clone with Git** (recommended for contributing or staying up to date)
   ```bash
   git clone https://github.com/<your-account>/escaperoom.git
   cd escaperoom
   ```

2. **Download the ZIP**
   - Visit your repository hosting page (e.g., GitHub) and click **Code → Download ZIP**.
   - Extract the archive and open it in your editor or terminal of choice.

## Quickstart

1. **Set Up the Environment**
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   - Copy `.env.example` to `.env` and set your Discord bot token:
     ```bash
     cp .env.example .env
     echo "DISCORD_TOKEN=your-token" >> .env
     ```
   - Optional environment variables:
     - `LOG_LEVEL` – defaults to `INFO`.
     - `ESCAPE_DB` – path to the SQLite database (defaults to `escape.db`).
     - `LEVELS_FILE` – path to the YAML levels file.

3. **Author or Review Levels**
   - Edit `levels.yaml` to customize puzzles, hints, and forward seeds.
   - Each level requires 2–4 hidden clues, 2–3 timed hints, and one or more accepted answers.

4. **Run the Bot**
   ```bash
   python bot.py
   ```
   The bot registers slash commands automatically. Invite it with the `applications.commands` scope (no message-content intent required).

## Slash Commands Overview
All commands live under `/escape`:

| Command | Description |
| --- | --- |
| `/escape start` | Enroll and deliver level 1 in a DM or private thread. |
| `/escape level` | Show the current level embed, progress, and hint status. |
| `/escape answer <text>` | Submit an answer; correct answers advance the level, wrong answers respect hint cooldowns. |
| `/escape hint` | Reveal the next available hint if its timer has expired. |
| `/escape leaderboard [scope]` | Show fastest completions for the guild or globally. |
| `/escape reset [user]` | (Admin) Reset a player’s progress. |
| `/escape skip [user]` | (Admin) Advance a player by one level. |
| `/escape status [user]` | (Mod) View a player’s level, hint usage, and stats. |
| `/escape config show` | (Admin) Display guild-specific configuration. |
| `/escape config set …` | (Admin) Update DM mode, hint interval, and lobby channel. |

## Customising Levels
Levels are fully data-driven:

```yaml
- id: 11
  title: "New Puzzle"
  description: "Your clue text here"
  answers: ["answer", "alternate answer"]
  hidden_clues:
    - "At least two hidden clues"
  timed_hints:
    - "Hints unlock every X minutes"
  forward_seeds:
    - "Optional breadcrumb for future levels"
```

Tips:
- Maintain unique `id` values and keep them in ascending order.
- For embedded prompts, add a `prompt_embed` section (title, description, footer).
- Hidden clues can leverage acrostics, zero-width characters, ciphers, or imagery.
- Forward seeds should foreshadow later solutions without spoiling them outright.

## Persistence & Anti-Cheat
- SQLite database (`escape.db` by default) stores players, progress, and attempts.
- Answer submissions are rate-limited to one every three seconds per user.
- Stored answers are hashed for auditing without exposing raw text.
- Per-guild configuration toggles DM mode, hint intervals, and lobby channels.

## Testing
Run unit tests locally to validate the YAML schema and answer matching utilities:
```bash
pytest
```

## Troubleshooting
- **Slash commands missing** – Ensure the bot was invited with the `applications.commands` scope and allow a few minutes for Discord to propagate commands. For immediate updates, use the `sync` method inside `discord.py` if necessary.
- **Missing intents or permissions** – The bot only needs the `members` intent (enabled by default for verified bots) and permission to create private threads or send DMs.
- **YAML validation errors** – The bot logs schema issues and exits. Validate via `pytest` or an online YAML linter before deploying.
- **Database locked** – SQLite can lock if multiple instances run simultaneously. Stop other bot instances or point `ESCAPE_DB` to a new file.

## Contributing
- Add new levels by editing `levels.yaml` and updating unit tests if schema rules change.
- Ensure `pytest` passes before committing.
- Format code with Black/PEP 8 guidelines (the repository follows `discord.py` conventions and includes inline type hints).

Happy escaping!
