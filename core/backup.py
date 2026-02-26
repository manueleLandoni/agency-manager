from __future__ import annotations

import base64
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import zipfile

from argon2.low_level import Type, hash_secret_raw
from cryptography.fernet import Fernet

from db.connection import DB_FILE

BACKUP_DIR = Path('backups')
WORK_TMP_DIR = Path('.backup_tmp')


def _resolved_backup_dir() -> Path:
    one_drive = (
        os.getenv('OneDrive')
        or os.getenv('OneDriveConsumer')
        or os.getenv('OneDriveCommercial')
    )
    if one_drive:
        return Path(one_drive) / 'Agency Manager' / 'backups'
    return BACKUP_DIR


def _sqlite_snapshot(source_db: Path, target_db: Path) -> None:
    """Create a consistent SQLite snapshot, including WAL changes."""
    target_db.parent.mkdir(parents=True, exist_ok=True)
    if target_db.exists():
        target_db.unlink()
    last_error: Exception | None = None
    for _ in range(8):
        try:
            with sqlite3.connect(source_db, timeout=10) as src_conn, sqlite3.connect(target_db, timeout=10) as dst_conn:
                src_conn.backup(dst_conn)
                dst_conn.execute('PRAGMA wal_checkpoint(FULL);')
            return
        except (PermissionError, OSError, sqlite3.OperationalError) as exc:
            last_error = exc
            time.sleep(0.12)
    if last_error:
        raise last_error


def _sqlite_snapshot_bytes(source_db: Path) -> bytes:
    """Create a consistent SQLite snapshot directly in memory and return raw DB bytes."""
    last_error: Exception | None = None
    for _ in range(8):
        try:
            with sqlite3.connect(source_db, timeout=10) as src_conn, sqlite3.connect(":memory:", timeout=10) as mem_conn:
                src_conn.backup(mem_conn)
                if hasattr(mem_conn, "serialize"):
                    return mem_conn.serialize()  # type: ignore[attr-defined]

                # Fallback for runtimes without serialize(): snapshot to a local temp file.
                with tempfile.TemporaryDirectory(dir=str(WORK_TMP_DIR.resolve())) as tmp:
                    tmp_db = Path(tmp) / "snapshot.db"
                    with sqlite3.connect(tmp_db, timeout=10) as dst_conn:
                        src_conn.backup(dst_conn)
                    return _read_bytes_with_retry(tmp_db)
        except (PermissionError, OSError, sqlite3.OperationalError) as exc:
            last_error = exc
            time.sleep(0.12)
    if last_error:
        raise last_error
    raise RuntimeError("Unable to create in-memory SQLite snapshot")


def _read_bytes_with_retry(path: Path) -> bytes:
    last_error: Exception | None = None
    for _ in range(80):
        try:
            return path.read_bytes()
        except (PermissionError, OSError) as exc:
            last_error = exc
            time.sleep(0.1)
    if last_error:
        raise last_error
    return b''


def _derive_backup_key(password: str, salt: bytes) -> bytes:
    raw = hash_secret_raw(
        secret=password.encode('utf-8'),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        type=Type.ID,
    )
    return base64.urlsafe_b64encode(raw)


def auto_backup(rotation: int = 10) -> Path | None:
    if not DB_FILE.exists():
        return None
    backup_dir = _resolved_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    target = backup_dir / f'auto_{stamp}.db'
    _sqlite_snapshot(DB_FILE, target)

    backups = sorted(backup_dir.glob('auto_*.db'), reverse=True)
    for old in backups[rotation:]:
        old.unlink(missing_ok=True)
    return target


def export_encrypted_backup(output_file: Path, password: str) -> Path:
    if not DB_FILE.exists():
        raise FileNotFoundError('Database not found')

    salt = Fernet.generate_key()[:16]
    key = _derive_backup_key(password, salt)
    fernet = Fernet(key)

    WORK_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(WORK_TMP_DIR.resolve())) as tmp:
        tmp_path = Path(tmp)
        db_bytes = _sqlite_snapshot_bytes(DB_FILE)
        meta = tmp_path / 'meta.json'
        meta.write_text(json.dumps({'created_at': datetime.now().isoformat()}), encoding='utf-8')

        zip_path = tmp_path / 'bundle.zip'
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('app.db', db_bytes)
            zf.write(meta, arcname='meta.json')

        encrypted = fernet.encrypt(zip_path.read_bytes())
        payload = {'salt': base64.b64encode(salt).decode('utf-8'), 'cipher': base64.b64encode(encrypted).decode('utf-8')}
        output_file.write_text(json.dumps(payload), encoding='utf-8')
        return output_file


def import_encrypted_backup(input_file: Path, password: str) -> None:
    payload = json.loads(input_file.read_text(encoding='utf-8'))
    salt = base64.b64decode(payload['salt'])
    cipher = base64.b64decode(payload['cipher'])
    key = _derive_backup_key(password, salt)
    fernet = Fernet(key)
    bundle = fernet.decrypt(cipher)

    WORK_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(WORK_TMP_DIR.resolve())) as tmp:
        zip_path = Path(tmp) / 'bundle.zip'
        zip_path.write_bytes(bundle)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extract('app.db', path=tmp)
        restored_db = Path(tmp) / 'app.db'
        temp_target = DB_FILE.with_suffix('.restored.tmp')
        shutil.copy2(restored_db, temp_target)

        # Replace DB atomically and clear WAL/SHM side files.
        os.replace(temp_target, DB_FILE)
        DB_FILE.with_name(f'{DB_FILE.name}-wal').unlink(missing_ok=True)
        DB_FILE.with_name(f'{DB_FILE.name}-shm').unlink(missing_ok=True)
