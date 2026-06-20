from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import json, os

app = Flask(__name__)
app.secret_key = 'alfath_secret_key_2026'

# ── USERS DATABASE ──────────────────────────────────────────────────────────
USERS = {
    'Taimoor': {
        'password': generate_password_hash('Farhana@1145'),
        'role': 'admin',
        'name': 'Taimoor',
    },
    'kadar': {
        'password': generate_password_hash('kadar123'),
        'role': 'user',
        'name': 'Kadar Ansari',
        'plan': 'free',
        'balance': 0,
        'peak': 0,
        'trades': 0,
        'wins': 0,
    },
    'amjad': {
        'password': generate_password_hash('amjad123'),
        'role': 'user',
        'name': 'Amjad Ansari',
        'plan': 'free',
        'balance': 0,
        'peak': 0,
        'trades': 0,
        'wins': 0,
    },
    'aamir': {
        'password': generate_password_hash('aamir123'),
        'role': 'user',
        'name': 'Aamir Choudhry',
        'plan': 'free',
        'balance': 0,
        'peak': 0,
        'trades': 0,
        'wins': 0,
    },
    'seharyab': {
        'password': generate_password_hash('seharyab123'),
        'role': 'user',
        'name': 'Seharyab Choudhry',
        'plan': 'free',
        'balance': 0,
        'peak': 0,
        'trades': 0,
        'wins': 0,
    },
}

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    if 'username' in session:
        if USERS[session['username']]['role'] == 'admin':
            return redirect(url_for('admin'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if username in USERS and check_password_hash(USERS[username]['password'], password):
            session['username'] = username
            if USERS[username]['role'] == 'admin':
                return redirect(url_for('admin'))
            return redirect(url_for('dashboard'))
        error = 'Invalid username or password'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    username = session['username']
    user = USERS[username]
    if user['role'] == 'admin':
        return redirect(url_for('admin'))
    return render_template('dashboard.html', user=user, username=username)

@app.route('/admin')
@login_required
def admin():
    username = session['username']
    if USERS[username]['role'] != 'admin':
        return redirect(url_for('dashboard'))
    users = {k:v for k,v in USERS.items() if v['role']=='user'}
    return render_template('admin.html', users=users)

@app.route('/api/status')
@login_required
def api_status():
    status_file = '/var/www/alfath/bot_status.json'
    try:
        with open(status_file, 'r') as f:
            data = json.load(f)
        return jsonify({
            'bot_status': 'RUNNING' if data.get('run_success') else 'ERROR',
            'rating': data.get('rating_display', 'N/A'),
            'rating_label': data.get('rating_label', ''),
            'fill_rate': data.get('fill_rate_pct', 0),
            'slippage': data.get('avg_slippage_bps', 0),
            'supervisor_block': data.get('supervisor_block_pct', 0),
            'trade_count': data.get('trade_count', 0),
            'pbo_supervised': data.get('pbo_supervised_pct', 0),
            'drifted_count': data.get('drifted_count', 0),
            'drifted_total': data.get('drifted_total', 0),
            'bot_mode': data.get('bot_mode', 'RESEARCH_BACKTEST_ONLY'),
            'live_trading': data.get('live_trading', False),
            'last_run_utc': data.get('last_run_utc', ''),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({
            'bot_status': 'STARTING',
            'rating': 'N/A',
            'fill_rate': 0,
            'slippage': 0,
            'supervisor_block': 0,
            'bot_mode': 'RESEARCH_BACKTEST_ONLY',
            'live_trading': False,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

