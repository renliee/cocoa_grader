"""Password verification and random cookie session helpers."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from db import read_connection, transaction

PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
LOGIN_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._@+-]{2,63}$')
SESSION_DAYS = 7


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def normalize_login(value):
    login = value.strip().lower()
    if not LOGIN_PATTERN.fullmatch(login):
        raise ValueError('Use a username or email containing 3–64 characters.')
    return login


def hash_token(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec='seconds')
    with transaction() as db:
        db.execute('INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at,created_at) VALUES (?,?,?,?,?)',
                   (hash_token(token), user_id, csrf, expires, utc_now()))
    return token, csrf


def get_session(token):
    if not token:
        return None
    with read_connection() as db:
        row = db.execute('''SELECT u.id,u.login,u.display_name,u.timezone,s.csrf_token,s.expires_at
                            FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?''', (hash_token(token),)).fetchone()
    if not row or row['expires_at'] <= utc_now():
        return None
    return dict(row)


def revoke_session(token):
    if token:
        with transaction() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (hash_token(token),))


def check_csrf(session, value):
    return bool(value) and hmac.compare_digest(session['csrf_token'], value)


def verify_password(stored_hash, password):
    try:
        return PASSWORDS.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False
