import os
import sqlite3
import datetime
import json
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['DATABASE'] = os.path.join(app.root_path, 'pennstate.db')
app.secret_key = 'dev_secret'  # For demo purposes only

# ---------- Database Helpers ----------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    with app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8'))
    db.commit()

# Seed sample games, achievements, trivia
def seed_data():
    db = get_db()
    # Games
    if db.execute('SELECT COUNT(*) FROM games').fetchone()[0] == 0:
        games = [
            ('Football', 'Penn State', 'Michigan', '2024-10-12 15:30', -150, 130, -3.5, 45.5, None),
            ('Basketball', 'Penn State', 'Ohio State', '2024-12-05 19:00', -110, -110, -2.5, 138.5, None)
        ]
        db.executemany('INSERT INTO games (sport, team1, team2, start_time, odds_team1, odds_team2, spread, over_under, result) VALUES (?,?,?,?,?,?,?,?,?)', games)
        db.commit()
    # Achievements
    if db.execute('SELECT COUNT(*) FROM achievements').fetchone()[0] == 0:
        ach = [
            ('First Bet Placed', 'Place your first bet.'),
            ('5 Wins in a Row', 'Win five bets in a row.')
        ]
        db.executemany('INSERT INTO achievements (name, description) VALUES (?,?)', ach)
        db.commit()
    # Trivia
    if db.execute('SELECT COUNT(*) FROM trivia').fetchone()[0] == 0:
        trivia = [
            ('What is the name of Penn State\'s mascot?', 'Nittany Lion'),
            ('In what town is Penn State located?', 'State College')
        ]
        db.executemany('INSERT INTO trivia (question, answer) VALUES (?,?)', trivia)
        db.commit()

# ---------- User Helpers ----------
def current_user():
    uid = session.get('user_id')
    if uid is None:
        return None
    db = get_db()
    return db.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()

def award_achievement(user_id, achievement_name):
    db = get_db()
    ach = db.execute('SELECT id FROM achievements WHERE name = ?', (achievement_name,)).fetchone()
    if ach:
        db.execute('INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) VALUES (?,?)', (user_id, ach['id']))
        db.commit()

# ---------- Routes ----------
@app.route('/')
def home():
    if current_user():
        return redirect(url_for('dashboard'))
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        if db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
            flash('Username already taken')
        else:
            db.execute('INSERT INTO users (username, password_hash) VALUES (?,?)',
                       (username, generate_password_hash(password)))
            db.commit()
            flash('Account created, please log in')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    db = get_db()
    games = db.execute('SELECT * FROM games WHERE result IS NULL').fetchall()
    trivia = db.execute('SELECT question FROM trivia ORDER BY RANDOM() LIMIT 1').fetchone()
    return render_template('dashboard.html', user=user, games=games, trivia=trivia['question'] if trivia else None)

@app.route('/place_bet/<int:game_id>', methods=['POST'])
def place_bet(game_id):
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    amount = int(request.form['amount'])
    bet_type = request.form['bet_type']
    choice = request.form['choice']
    db = get_db()
    game = db.execute('SELECT * FROM games WHERE id=?', (game_id,)).fetchone()
    if game and amount > 0 and user['balance'] >= amount:
        odds = game['odds_team1'] if choice == game['team1'] else game['odds_team2']
        db.execute('INSERT INTO bets (user_id, game_id, amount, bet_type, choice, odds) VALUES (?,?,?,?,?,?)',
                   (user['id'], game_id, amount, bet_type, choice, odds))
        db.execute('UPDATE users SET balance = balance - ? WHERE id=?', (amount, user['id']))
        db.commit()
        # First bet achievement
        count = db.execute('SELECT COUNT(*) FROM bets WHERE user_id=?', (user['id'],)).fetchone()[0]
        if count == 1:
            award_achievement(user['id'], 'First Bet Placed')
        flash('Bet placed!')
    else:
        flash('Insufficient balance or invalid game')
    return redirect(url_for('dashboard'))

@app.route('/history')
def history():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    db = get_db()
    bets = db.execute('SELECT b.*, g.team1, g.team2 FROM bets b JOIN games g ON b.game_id=g.id WHERE b.user_id=? ORDER BY b.id DESC', (user['id'],)).fetchall()
    return render_template('history.html', bets=bets, user=user)

@app.route('/leaderboard')
def leaderboard():
    db = get_db()
    leaders = db.execute('SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10').fetchall()
    return render_template('leaderboard.html', leaders=leaders)

@app.route('/daily_bonus')
def daily_bonus():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    today = datetime.date.today().isoformat()
    if user['last_bonus'] != today:
        db = get_db()
        db.execute('UPDATE users SET balance = balance + 100, last_bonus=? WHERE id=?', (today, user['id']))
        db.commit()
        flash('Daily bonus claimed!')
    else:
        flash('Bonus already claimed today')
    return redirect(url_for('dashboard'))

@app.route('/process_results')
def process_results():
    """Mock endpoint to process finished games and update bets."""
    db = get_db()
    games = db.execute('SELECT * FROM games WHERE result IS NOT NULL').fetchall()
    for game in games:
        bets = db.execute('SELECT * FROM bets WHERE game_id=? AND result="pending"', (game['id'],)).fetchall()
        for bet in bets:
            win = False
            if bet['bet_type'] == 'moneyline' and bet['choice'] == game['result']:
                win = True
            # Simplified - ignoring spread/over_under calculations
            payout = int(bet['amount'] * (abs(bet['odds'])/100)) if win else 0
            db.execute('UPDATE bets SET result=?, payout=? WHERE id=?', ('win' if win else 'loss', payout, bet['id']))
            if win:
                db.execute('UPDATE users SET balance = balance + ?, wins_in_row = wins_in_row + 1 WHERE id=?', (bet['amount'] + payout, bet['user_id']))
            else:
                db.execute('UPDATE users SET wins_in_row = 0 WHERE id=?', (bet['user_id'],))
            # Achievement for 5 wins in a row
            wins = db.execute('SELECT wins_in_row FROM users WHERE id=?', (bet['user_id'],)).fetchone()['wins_in_row']
            if wins >= 5:
                award_achievement(bet['user_id'], '5 Wins in a Row')
        db.commit()
    flash('Results processed')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    if not os.path.exists(app.config['DATABASE']):
        with app.app_context():
            init_db()
            seed_data()
    app.run(debug=True)
