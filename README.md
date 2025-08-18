# Yahoo Fantasy Discord Bot

Discord bot and OAuth server enabling multi-user Yahoo Fantasy Football commands.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a Yahoo developer application and set the redirect URI to `${PUBLIC_BASE_URL}${YAHOO_REDIRECT_PATH}`.
3. Copy `.env.example` to `.env` and fill in your credentials.

## Running

Start the OAuth server and the bot in separate processes:

```bash
uvicorn auth_server:app --port $PORT
python bot.py
```

During development expose the auth server via a tunnel such as ngrok and set `PUBLIC_BASE_URL` to the public URL.

## Commands

- `/link_yahoo` – link your Yahoo account.
- `/pick_league` – list leagues you belong to.
- `/set_league_key <key>` – set the league for the current server.
- `/standings` – show league standings.
- `/matchups [week]` – display matchups for a week.
- `/roster <team>` – show a team roster.
- `/unlink_yahoo` – remove stored Yahoo credentials.

## Testing

```bash
pytest
```
