from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import eventlet
from flask_mysqldb import MySQL
from db_config import get_db_connection
import uuid
import datetime

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

# In-memory user tracking for sessions (for demo)
session_users = {}

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

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

# Ensure all protected routes redirect to login if not authenticated
@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username=%s', (session['username'],))
    user = cur.fetchone()
    sessions_list = []
    if user:
        user_id = user[0]
        cur.execute('SELECT session_id, created_at FROM sessions WHERE owner_id=%s ORDER BY created_at DESC', (user_id,))
        sessions_list = cur.fetchall()
    conn.close()
    return render_template('dashboard.html', username=session['username'], sessions=sessions_list)

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

@socketio.on('join_file')
def handle_join_file(data=None):
    session_id = data.get('session_id') if data and 'session_id' in data else None
    file = data.get('file') if data and 'file' in data else None
    username = session.get('username')
    room = f"{session_id}:{file}"
    join_room(room)
    if session_id not in session_users:
        session_users[session_id] = set()
    session_users[session_id].add(username)
    emit('user_list', list(session_users[session_id]), to=session_id)

@socketio.on('leave_file')
def handle_leave_file(data=None):
    session_id = data.get('session_id') if data and 'session_id' in data else None
    file = data.get('file') if data and 'file' in data else None
    username = session.get('username')
    room = f"{session_id}:{file}"
    leave_room(room)
    if session_id in session_users and username in session_users[session_id]:
        session_users[session_id].remove(username)
        emit('user_list', list(session_users[session_id]), to=session_id)

@socketio.on('code_change')
def handle_code_change(data=None):
    session_id = data.get('session_id') if data and 'session_id' in data else None
    file = data.get('file') if data and 'file' in data else None
    code = data.get('code') if data and 'code' in data else None
    room = f"{session_id}:{file}"
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE files SET content=%s WHERE session_id=%s AND filename=%s', (code, session_id, file))
    conn.commit()
    conn.close()
    emit('code_update', {'file': file, 'code': code}, to=room, include_self=False)

@socketio.on('request_code')
def handle_request_code(data=None):
    session_id = data.get('session_id') if data and 'session_id' in data else None
    file = data.get('file') if data and 'file' in data else None
    room = f"{session_id}:{file}"
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT content FROM files WHERE session_id=%s AND filename=%s', (session_id, file))
    row = cur.fetchone()
    conn.close()
    code = row[0] if row else ''
    emit('code_update', {'file': file, 'code': code}, to=room)

# API: Get last 50 chat messages for a session
@app.route('/api/session/<session_id>/chats', methods=['GET'])
def api_get_chats(session_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT user, message, timestamp FROM chats WHERE session_id=%s ORDER BY timestamp DESC LIMIT 50', (session_id,))
    messages = [
        {'user': row[0], 'message': row[1], 'time': row[2].strftime('%H:%M')}
        for row in reversed(cur.fetchall())
    ]
    conn.close()
    return jsonify({'messages': messages})

@socketio.on('chat_message')
def handle_chat_message(data=None):
    session_id = data.get('session_id') if data and 'session_id' in data else None
    user = data.get('user') if data and 'user' in data else None
    message = data.get('message') if data and 'message' in data else None
    time = datetime.datetime.now().strftime('%H:%M')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO chats (session_id, user, message) VALUES (%s, %s, %s)', (session_id, user, message))
    conn.commit()
    conn.close()
    emit('chat_message', {'user': user, 'message': message, 'time': time}, to=session_id)

@socketio.on('join_session')
def handle_join_session(data=None):
    session_id = data.get('session_id') if data and 'session_id' in data else None
    username = session.get('username')
    join_room(session_id)
    if session_id not in session_users:
        session_users[session_id] = set()
    session_users[session_id].add(username)
    emit('user_list', list(session_users[session_id]), to=session_id)

@socketio.on('leave_session')
def handle_leave_session(data=None):
    session_id = data.get('session_id') if data and 'session_id' in data else None
    username = session.get('username')
    leave_room(session_id)
    if session_id in session_users and username in session_users[session_id]:
        session_users[session_id].remove(username)
        emit('user_list', list(session_users[session_id]), to=session_id)

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['username'])

# API: List files in a session
@app.route('/api/session/<session_id>/files', methods=['GET'])
def api_list_files(session_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT filename FROM files WHERE session_id=%s ORDER BY filename', (session_id,))
    files = [row[0] for row in cur.fetchall()]
    conn.close()
    return jsonify({'files': files})

# API: Create a new file in a session
@app.route('/api/session/<session_id>/files', methods=['POST'])
def api_create_file(session_id):
    filename = request.json.get('filename')
    if not filename:
        return jsonify({'error': 'Filename required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO files (session_id, filename, content) VALUES (%s, %s, %s)', (session_id, filename, ''))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400
    conn.close()
    return jsonify({'success': True})

# API: Get file content
@app.route('/api/session/<session_id>/file/<filename>', methods=['GET'])
def api_get_file(session_id, filename):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT content FROM files WHERE session_id=%s AND filename=%s', (session_id, filename))
    row = cur.fetchone()
    conn.close()
    if row:
        return jsonify({'content': row[0]})
    else:
        return jsonify({'error': 'File not found'}), 404

# API: Save/update file content
@app.route('/api/session/<session_id>/file/<filename>', methods=['POST'])
def api_save_file(session_id, filename):
    content = request.json.get('content', '')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE files SET content=%s WHERE session_id=%s AND filename=%s', (content, session_id, filename))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# API: Delete a file
@app.route('/api/session/<session_id>/file/<filename>', methods=['DELETE'])
def api_delete_file(session_id, filename):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM files WHERE session_id=%s AND filename=%s', (session_id, filename))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# API: Rename a file
@app.route('/api/session/<session_id>/file/<filename>/rename', methods=['POST'])
def api_rename_file(session_id, filename):
    new_filename = request.json.get('new_filename')
    if not new_filename:
        return jsonify({'error': 'New filename required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE files SET filename=%s WHERE session_id=%s AND filename=%s', (new_filename, session_id, filename))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000) 