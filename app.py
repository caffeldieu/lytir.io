"""
Lytir.io Backend API
A forecasting platform backend built with Flask
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import sqlite3
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'lytir.io')

# Configure CORS - UPDATE THIS WITH YOUR FRONTEND URL WHEN DEPLOYING
CORS(app, supports_credentials=True, origins=[
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://your-frontend-url.repl.co',  # Add this!
    'https://your-frontend-url.netlify.app',  # Or this!
])

# Database initialization
def init_db():
    conn = sqlite3.connect('lytir.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  email TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  tokens INTEGER DEFAULT 1000,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Markets table
    c.execute('''CREATE TABLE IF NOT EXISTS markets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  question TEXT NOT NULL,
                  description TEXT,
                  category TEXT,
                  resolution_date TEXT,
                  status TEXT DEFAULT 'active',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Forecasts table
    c.execute('''CREATE TABLE IF NOT EXISTS forecasts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  market_id INTEGER NOT NULL,
                  probability REAL NOT NULL,
                  tokens_spent INTEGER DEFAULT 10,
                  reward INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users(id),
                  FOREIGN KEY (market_id) REFERENCES markets(id))''')
    
    conn.commit()
    
    # Add sample markets if none exist
    c.execute('SELECT COUNT(*) FROM markets')
    if c.fetchone()[0] == 0:
        sample_markets = [
            ("Will Ireland qualify for FIFA 2026?", 
             "This market resolves YES if Ireland's national football team qualifies for the 2026 FIFA World Cup by the end of qualifying rounds.",
             "Sports", "2026-06-30"),
            ("Will Sinn Féin win next election?",
             "This market resolves YES if Sinn Féin becomes the largest party in the next Irish general election.",
             "Politics", "2025-12-31"),
            ("Will Irish tech startup IPO in 2025?",
             "This market resolves YES if any Irish-founded tech startup goes public in 2025.",
             "Tech", "2025-12-31")
        ]
        c.executemany('INSERT INTO markets (question, description, category, resolution_date) VALUES (?, ?, ?, ?)',
                     sample_markets)
        conn.commit()
    
    conn.close()

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Helper functions
def get_db():
    conn = sqlite3.connect('lytir.db')
    conn.row_factory = sqlite3.Row
    return conn

def calculate_crowd_prediction(market_id):
    """Calculate average prediction for a market"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT AVG(probability) as avg_prob, COUNT(*) as count 
                 FROM forecasts WHERE market_id = ?''', (market_id,))
    result = c.fetchone()
    conn.close()
    
    if result and result['count'] > 0:
        return round(result['avg_prob'], 0), result['count']
    return 50, 0  # Default if no forecasts

def calculate_user_accuracy(user_id):
    """Calculate user's forecasting accuracy"""
    conn = get_db()
    c = conn.cursor()
    
    # Get resolved forecasts with their markets
    c.execute('''SELECT f.probability, m.status 
                 FROM forecasts f 
                 JOIN markets m ON f.market_id = m.id 
                 WHERE f.user_id = ? AND m.status = 'resolved' ''', (user_id,))
    
    forecasts = c.fetchall()
    conn.close()
    
    if not forecasts:
        return 0
    
    # Simple accuracy calculation (can be improved with Brier score)
    total_accuracy = 0
    for forecast in forecasts:
        # Placeholder: In real implementation, compare with actual outcome
        total_accuracy += abs(100 - forecast['probability'])
    
    return round(100 - (total_accuracy / len(forecasts)), 0)

# ========================================
# AUTHENTICATION ENDPOINTS
# ========================================

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    if not all([username, email, password]):
        return jsonify({'error': 'All fields required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Check if user exists
    c.execute('SELECT id FROM users WHERE email = ? OR username = ?', (email, username))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'User already exists'}), 400
    
    # Create user
    password_hash = generate_password_hash(password)
    c.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
              (username, email, password_hash))
    conn.commit()
    user_id = c.lastrowid
    
    c.execute('SELECT id, username, email, tokens FROM users WHERE id = ?', (user_id,))
    user = dict(c.fetchone())
    conn.close()
    
    # Set session
    session['user_id'] = user_id
    session.permanent = True
    
    return jsonify({
        'message': 'Account created successfully',
        'user': user
    }), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not all([email, password]):
        return jsonify({'error': 'Email and password required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = c.fetchone()
    conn.close()
    
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Set session
    session['user_id'] = user['id']
    session.permanent = True
    
    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'tokens': user['tokens']
        }
    }), 200

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out successfully'}), 200

# ========================================
# USER ENDPOINTS
# ========================================

@app.route('/api/user', methods=['GET'])
@login_required
def get_user():
    user_id = session['user_id']
    
    conn = get_db()
    c = conn.cursor()
    
    # Get user data
    c.execute('SELECT id, username, email, tokens FROM users WHERE id = ?', (user_id,))
    user = dict(c.fetchone())
    
    # Get forecasts count
    c.execute('SELECT COUNT(*) as count FROM forecasts WHERE user_id = ?', (user_id,))
    user['forecasts_count'] = c.fetchone()['count']
    
    # Calculate accuracy
    user['accuracy'] = calculate_user_accuracy(user_id)
    
    # Calculate rank (simple implementation)
    c.execute('''SELECT COUNT(*) + 1 as rank FROM users 
                 WHERE tokens > (SELECT tokens FROM users WHERE id = ?)''', (user_id,))
    user['rank'] = c.fetchone()['rank']
    
    conn.close()
    
    return jsonify(user), 200

@app.route('/api/user/forecasts', methods=['GET'])
@login_required
def get_user_forecasts():
    user_id = session['user_id']
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT f.*, m.question as market_question, m.status, m.category
                 FROM forecasts f
                 JOIN markets m ON f.market_id = m.id
                 WHERE f.user_id = ?
                 ORDER BY f.created_at DESC''', (user_id,))
    
    forecasts = []
    for row in c.fetchall():
        forecast = dict(row)
        # Get crowd prediction for this market
        crowd_pred, _ = calculate_crowd_prediction(forecast['market_id'])
        forecast['crowd_prediction'] = crowd_pred
        forecasts.append(forecast)
    
    conn.close()
    
    return jsonify(forecasts), 200

# ========================================
# MARKET ENDPOINTS
# ========================================

@app.route('/api/markets', methods=['GET'])
def get_markets():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM markets WHERE status = "active" ORDER BY created_at DESC')
    
    markets = []
    for row in c.fetchall():
        market = dict(row)
        # Add crowd prediction and forecast count
        crowd_pred, forecast_count = calculate_crowd_prediction(market['id'])
        market['crowd_prediction'] = crowd_pred
        market['forecasts_count'] = forecast_count
        markets.append(market)
    
    conn.close()
    
    return jsonify(markets), 200

@app.route('/api/markets/<int:market_id>', methods=['GET'])
def get_market(market_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM markets WHERE id = ?', (market_id,))
    market_row = c.fetchone()
    
    if not market_row:
        conn.close()
        return jsonify({'error': 'Market not found'}), 404
    
    market = dict(market_row)
    
    # Add crowd prediction and forecast count
    crowd_pred, forecast_count = calculate_crowd_prediction(market_id)
    market['crowd_prediction'] = crowd_pred
    market['forecasts_count'] = forecast_count
    
    # Get recent forecasts
    c.execute('''SELECT f.probability, f.created_at, u.username
                 FROM forecasts f
                 JOIN users u ON f.user_id = u.id
                 WHERE f.market_id = ?
                 ORDER BY f.created_at DESC
                 LIMIT 10''', (market_id,))
    
    market['recent_forecasts'] = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    return jsonify(market), 200

# ========================================
# FORECAST ENDPOINTS
# ========================================

@app.route('/api/forecast', methods=['POST'])
@login_required
def submit_forecast():
    user_id = session['user_id']
    data = request.get_json()
    
    market_id = data.get('market_id')
    probability = data.get('probability')
    
    if not all([market_id, probability is not None]):
        return jsonify({'error': 'Market ID and probability required'}), 400
    
    if not 0 <= probability <= 100:
        return jsonify({'error': 'Probability must be between 0 and 100'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Check if market exists and is active
    c.execute('SELECT status FROM markets WHERE id = ?', (market_id,))
    market = c.fetchone()
    if not market:
        conn.close()
        return jsonify({'error': 'Market not found'}), 404
    
    if market['status'] != 'active':
        conn.close()
        return jsonify({'error': 'Market is not active'}), 400
    
    # Check user has enough tokens
    c.execute('SELECT tokens FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    tokens_cost = 10
    
    if user['tokens'] < tokens_cost:
        conn.close()
        return jsonify({'error': 'Insufficient tokens'}), 400
    
    # Create forecast
    c.execute('''INSERT INTO forecasts (user_id, market_id, probability, tokens_spent)
                 VALUES (?, ?, ?, ?)''', (user_id, market_id, probability, tokens_cost))
    
    # Deduct tokens
    c.execute('UPDATE users SET tokens = tokens - ? WHERE id = ?', (tokens_cost, user_id))
    
    conn.commit()
    forecast_id = c.lastrowid
    conn.close()
    
    return jsonify({
        'message': 'Forecast submitted successfully',
        'forecast_id': forecast_id
    }), 201

# ========================================
# LEADERBOARD ENDPOINT
# ========================================

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''SELECT id, username, tokens, 
                 (SELECT COUNT(*) FROM forecasts WHERE user_id = users.id) as forecasts_count
                 FROM users
                 ORDER BY tokens DESC
                 LIMIT 50''')
    
    leaderboard = []
    for row in c.fetchall():
        user = dict(row)
        user['accuracy'] = calculate_user_accuracy(user['id'])
        leaderboard.append(user)
    
    conn.close()
    
    return jsonify(leaderboard), 200

# ========================================
# ADMIN ENDPOINTS (for testing)
# ========================================

@app.route('/api/admin/resolve-market', methods=['POST'])
def resolve_market():
    """Admin endpoint to resolve markets"""
    data = request.get_json()
    market_id = data.get('market_id')
    outcome = data.get('outcome')  # 'yes' or 'no'
    
    if not all([market_id, outcome]):
        return jsonify({'error': 'Market ID and outcome required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Update market status
    c.execute('UPDATE markets SET status = ? WHERE id = ?', ('resolved', market_id))
    
    # Calculate rewards for forecasters
    c.execute('SELECT * FROM forecasts WHERE market_id = ?', (market_id,))
    forecasts = c.fetchall()
    
    for forecast in forecasts:
        # Simple reward calculation based on accuracy
        if outcome == 'yes':
            accuracy = forecast['probability']
        else:
            accuracy = 100 - forecast['probability']
        
        # Calculate reward (more accurate = more tokens)
        reward = int(accuracy * 0.5)  # Max 50 tokens for perfect prediction
        
        # Update forecast reward
        c.execute('UPDATE forecasts SET reward = ? WHERE id = ?', (reward, forecast['id']))
        
        # Give tokens to user
        c.execute('UPDATE users SET tokens = tokens + ? WHERE id = ?', 
                 (reward, forecast['user_id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Market resolved successfully'}), 200

# ========================================
# HEALTH CHECK
# ========================================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/', methods=['GET'])
def root():
    return jsonify({
        'message': 'Lytir.io API',
        'version': '1.0.0',
        'endpoints': {
            'auth': ['/api/signup', '/api/login', '/api/logout'],
            'user': ['/api/user', '/api/user/forecasts'],
            'markets': ['/api/markets', '/api/markets/<id>'],
            'forecast': ['/api/forecast'],
            'leaderboard': ['/api/leaderboard']
        }
    }), 200

# ========================================
# RUN SERVER
# ========================================

if __name__ == '__main__':
    init_db()
    # Use 0.0.0.0 for deployment, localhost for local development
    # Change port if needed (default 5001)
    app.run(host='0.0.0.0', port=5001, debug=True)
