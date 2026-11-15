"""SQLite persistence for demo accounts, sessions and delivery orders."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get('CAMPUSFLEET_DB', Path(__file__).with_name('campusfleet.sqlite3')))


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                salt BLOB NOT NULL, password_hash BLOB NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                created_at REAL NOT NULL, status TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkout_tickets (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                order_id TEXT NOT NULL REFERENCES orders(id), expires_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS orders_user_time ON orders(user_id, created_at DESC);
        ''')


def register(username, password):
    if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_]{3,32}', username):
        raise ValueError('用户名须为 3 至 32 位字母、数字或下划线')
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise ValueError('密码须为 8 至 128 个字符')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=16384, r=8, p=1)
    user_id = 'CF-U-' + secrets.token_hex(8).upper()
    try:
        with connect() as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?,?)',
                       (user_id, username, salt, digest, time.time()))
    except sqlite3.IntegrityError as error:
        raise ValueError('用户名已被使用') from error
    return {'id': user_id, 'username': username}


def login(username, password):
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError('用户名或密码错误')
    with connect() as db:
        row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
    if row is None or not hmac.compare_digest(
        row['password_hash'], hashlib.scrypt(password.encode('utf-8'), salt=row['salt'], n=16384, r=8, p=1)
    ):
        raise ValueError('用户名或密码错误')
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('INSERT INTO sessions VALUES (?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(), row['id'], time.time() + 30 * 86400))
    return {'token': token, 'user': {'id': row['id'], 'username': row['username']}}


def user_for_token(token):
    if not token:
        return None
    with connect() as db:
        row = db.execute('''SELECT users.id, users.username, NULL AS checkout_order_id FROM sessions
            JOIN users ON users.id=sessions.user_id
            WHERE sessions.token_hash=? AND sessions.expires_at>?''',
            (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if row is None:
            row = db.execute('''SELECT users.id, users.username, checkout_tickets.order_id AS checkout_order_id
                FROM checkout_tickets JOIN users ON users.id=checkout_tickets.user_id
                WHERE checkout_tickets.token_hash=? AND checkout_tickets.expires_at>?''',
                (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    return dict(row) if row else None


def create_checkout_ticket(user_id, order_id):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('DELETE FROM checkout_tickets WHERE expires_at<=?', (time.time(),))
        db.execute('INSERT INTO checkout_tickets VALUES(?,?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(), user_id, order_id, time.time() + 1800))
    return token


def logout(token):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))


def save_order(task):
    payload = {key: value for key, value in task.items() if key != '_started_at'}
    with connect() as db:
        db.execute('''INSERT INTO orders(id,user_id,created_at,status,payload) VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload''',
            (task['id'], task['user_id'], task['created_at'], task['status'],
             json.dumps(payload, ensure_ascii=False)))


def load_orders():
    with connect() as db:
        rows = db.execute('SELECT payload FROM orders ORDER BY created_at').fetchall()
    return [json.loads(row['payload']) for row in rows]
