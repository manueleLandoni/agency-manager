from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import secrets
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from core.crypto import CryptoManager
from db.connection import get_connection

REMEMBER_TOKEN_FILE = Path('.remember_token')
DATA_KEY_CACHE_FILE = Path('.data_key_cache')


@dataclass
class SessionUser:
    id: int
    username: str
    role: str
    can_view_passwords: bool
    data_key: bytes


class AuthService:
    def __init__(self) -> None:
        self.ph = PasswordHasher()

    def ensure_default_admin(self) -> None:
        with get_connection() as conn:
            row = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()
            if row['c'] > 0:
                return

        salt = CryptoManager.random_salt()
        user_key = CryptoManager.derive_user_key('admin123!', salt)
        data_key = CryptoManager.generate_data_key()
        wrapped_data_key = CryptoManager.wrap_data_key(data_key, user_key)

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO users(username, password_hash, role, can_view_passwords, crypto_salt, wrapped_data_key)
                VALUES (?, ?, 'admin', 1, ?, ?)
                """,
                ('admin', self.ph.hash('admin123!'), salt, wrapped_data_key),
            )

    def create_user_with_data_key(
        self,
        username: str,
        password: str,
        role: str,
        can_view_passwords: bool,
        data_key: bytes,
    ) -> int:
        salt = CryptoManager.random_salt()
        user_key = CryptoManager.derive_user_key(password, salt)
        wrapped_data_key = CryptoManager.wrap_data_key(data_key, user_key)
        password_hash = self.ph.hash(password)

        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO users(username, password_hash, role, can_view_passwords, crypto_salt, wrapped_data_key)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username, password_hash, role, 1 if can_view_passwords else 0, salt, wrapped_data_key),
            )
            return int(cur.lastrowid)

    def list_users(self) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                'SELECT id, username, role, can_view_passwords, is_active, created_at FROM users ORDER BY username'
            ).fetchall()
            return [dict(r) for r in rows]

    def update_user_flags(self, user_id: int, role: str, can_view_passwords: bool, is_active: bool) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET role = ?, can_view_passwords = ?, is_active = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (role, 1 if can_view_passwords else 0, 1 if is_active else 0, user_id),
            )

    def login(self, username: str, password: str) -> SessionUser | None:
        with get_connection() as conn:
            row = conn.execute(
                'SELECT * FROM users WHERE username = ? AND is_active = 1',
                (username,),
            ).fetchone()
            if row is None:
                return None
            try:
                self.ph.verify(row['password_hash'], password)
            except VerifyMismatchError:
                return None

            user_key = CryptoManager.derive_user_key(password, row['crypto_salt'])
            data_key = CryptoManager.unwrap_data_key(row['wrapped_data_key'], user_key)
            return SessionUser(
                id=row['id'],
                username=row['username'],
                role=row['role'],
                can_view_passwords=bool(row['can_view_passwords']),
                data_key=data_key,
            )

    def issue_remember_token(self, user_id: int, days_valid: int = 30) -> str:
        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=days_valid)).isoformat()

        with get_connection() as conn:
            conn.execute(
                'INSERT INTO remember_tokens(user_id, token_hash, expires_at, revoked) VALUES (?, ?, ?, 0)',
                (user_id, token_hash, expires_at),
            )
        return token

    def revoke_remember_token(self, token: str | None) -> None:
        if not token:
            return
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        with get_connection() as conn:
            conn.execute('UPDATE remember_tokens SET revoked = 1 WHERE token_hash = ?', (token_hash,))

    def login_from_remember_token(self, token: str) -> SessionUser | None:
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT u.* FROM remember_tokens rt
                JOIN users u ON u.id = rt.user_id
                WHERE rt.token_hash = ?
                  AND rt.revoked = 0
                  AND datetime(rt.expires_at) >= datetime('now')
                  AND u.is_active = 1
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None

            data_key = self._load_cached_data_key(row['username'])
            if not data_key:
                return None

            return SessionUser(
                id=row['id'],
                username=row['username'],
                role=row['role'],
                can_view_passwords=bool(row['can_view_passwords']),
                data_key=data_key,
            )

    def cache_data_key(self, username: str, data_key: bytes) -> None:
        machine_key = self._machine_key()
        encrypted = CryptoManager.wrap_data_key(data_key, machine_key)
        payload = {'username': username, 'data_key': encrypted.decode('utf-8')}
        DATA_KEY_CACHE_FILE.write_text(json.dumps(payload), encoding='utf-8')

    def _load_cached_data_key(self, username: str) -> bytes | None:
        if not DATA_KEY_CACHE_FILE.exists():
            return None
        try:
            payload = json.loads(DATA_KEY_CACHE_FILE.read_text(encoding='utf-8'))
            if payload.get('username') != username:
                return None
            machine_key = self._machine_key()
            return CryptoManager.unwrap_data_key(payload['data_key'].encode('utf-8'), machine_key)
        except Exception:
            return None

    def clear_cached_data_key(self) -> None:
        DATA_KEY_CACHE_FILE.unlink(missing_ok=True)

    def _machine_key(self) -> bytes:
        digest = hashlib.sha256((Path.home().as_posix() + '-agency-manager').encode('utf-8')).digest()
        return base64.urlsafe_b64encode(digest)


def save_remember_token(token: str) -> None:
    REMEMBER_TOKEN_FILE.write_text(json.dumps({'token': token}), encoding='utf-8')


def load_remember_token() -> str | None:
    if not REMEMBER_TOKEN_FILE.exists():
        return None
    try:
        payload = json.loads(REMEMBER_TOKEN_FILE.read_text(encoding='utf-8'))
        return payload.get('token')
    except Exception:
        return None


def clear_remember_token_file() -> None:
    REMEMBER_TOKEN_FILE.unlink(missing_ok=True)
