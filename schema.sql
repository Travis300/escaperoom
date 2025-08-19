-- users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    balance INTEGER NOT NULL DEFAULT 1000,
    last_bonus TEXT,
    wins_in_row INTEGER DEFAULT 0
);

-- games table
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    team1 TEXT NOT NULL,
    team2 TEXT NOT NULL,
    start_time TEXT NOT NULL,
    odds_team1 REAL NOT NULL,
    odds_team2 REAL NOT NULL,
    spread REAL,
    over_under REAL,
    result TEXT
);

-- bets table
CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    game_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    bet_type TEXT NOT NULL,
    choice TEXT NOT NULL,
    odds REAL NOT NULL,
    result TEXT DEFAULT 'pending',
    payout INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(game_id) REFERENCES games(id)
);

-- achievements
CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_achievements (
    user_id INTEGER,
    achievement_id INTEGER,
    PRIMARY KEY(user_id, achievement_id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(achievement_id) REFERENCES achievements(id)
);

-- trivia
CREATE TABLE IF NOT EXISTS trivia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL
);
