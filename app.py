from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
import eventlet
from flask_mysqldb import MySQL
from db_config import get_db_connection
import uuid

# Check DB connection at startup
try:
    conn = get_db_connection()
    conn.close()
    print('Database connection successful!')
except Exception as e:
    print(f'Failed to connect to database: {e}')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# MySQL configuration
app.config['MYSQL_HOST'] = 'test.schooldesk.org'
app.config['MYSQL_USER'] = 'ANSK'
app.config['MYSQL_PASSWORD'] = 'Nick8956'
app.config['MYSQL_DB'] = 'devHub'

mysql = MySQL(app)

# In-memory user store (for demo)
users = {}

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()
        # Check if username exists
        cur.execute('SELECT id FROM users WHERE username=%s', (username,))
        if cur.fetchone():
            conn.close()
            flash('Username already exists!')
            return render_template('signup.html')
        # Insert new user
        password_hash = generate_password_hash(password)
        cur.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s)', (username, password_hash))
        conn.commit()
        conn.close()
        flash('Signup successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'])

@app.route('/create_session', methods=['POST'])
def create_session():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    # Get user id
    cur.execute('SELECT id FROM users WHERE username=%s', (session['username'],))
    user = cur.fetchone()
    if not user:
        conn.close()
        return redirect(url_for('dashboard'))
    user_id = user[0]
    session_id = str(uuid.uuid4())[:8]
    cur.execute('INSERT INTO sessions (session_id, owner_id) VALUES (%s, %s)', (session_id, user_id))
    conn.commit()
    conn.close()
    return redirect(url_for('coding_session', session_id=session_id))

@app.route('/join_session', methods=['POST'])
def join_session():
    if 'username' not in session:
        return redirect(url_for('login'))
    session_id = request.form['session_id']
    # Optionally, check if session exists
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id FROM sessions WHERE session_id=%s', (session_id,))
    session_row = cur.fetchone()
    conn.close()
    if not session_row:
        flash('Session not found!')
        return redirect(url_for('dashboard'))
    return redirect(url_for('coding_session', session_id=session_id))

@app.route('/session/<session_id>')
def coding_session(session_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['username'], session_id=session_id)

# Update login to redirect to dashboard
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # DB lookup
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT password_hash FROM users WHERE username=%s', (username,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user[0], password):
            session['username'] = username
            return redirect(url_for('dashboard'))
        flash('Invalid username or password!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logged out successfully!')
    return redirect(url_for('login'))

# Store code in memory (for demo; use a database for production)
shared_code = {'content': ''}

@socketio.on('code_change')
def handle_code_change(data):
    shared_code['content'] = data['code']
    emit('code_update', {'code': data['code']}, broadcast=True, include_self=False)

@socketio.on('request_code')
def handle_request_code():
    emit('code_update', {'code': shared_code['content']})

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['username'])

if __name__ == '__main__':
    socketio.run(app, debug=True) 