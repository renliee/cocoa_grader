"""SQLite connections, numbered migrations, and short write transactions."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get('KAKAO_DATA_DIR', Path(__file__).resolve().parent.parent / 'data')).resolve()
DB_PATH = DATA_DIR / 'kakaolens.sqlite3'
MIGRATIONS = Path(__file__).resolve().parent / 'migrations'
FK_REBUILD_MIGRATIONS = {'002_optional_supplier'}


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    db.execute('PRAGMA journal_mode=WAL')
    return db


def migrate():
    db = connect()
    try:
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        applied = {row['version'] for row in db.execute('SELECT version FROM schema_migrations')}
        for file in sorted(MIGRATIONS.glob('*.sql')):
            if file.stem in applied:
                continue
            version = file.stem.replace("'", "''")
            script = file.read_text(encoding='utf-8')
            rebuild = file.stem in FK_REBUILD_MIGRATIONS
            if rebuild:
                db.execute('PRAGMA foreign_keys=OFF')
            try:
                db.executescript(f"BEGIN IMMEDIATE;\n{script}\nINSERT INTO schema_migrations(version) VALUES ('{version}');")
                violations = db.execute('PRAGMA foreign_key_check').fetchall()
                if violations:
                    raise sqlite3.IntegrityError(f'Migration {file.stem} produced foreign-key violations: {violations}')
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                if rebuild:
                    db.execute('PRAGMA foreign_keys=ON')
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def read_connection():
    db = connect()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def transaction():
    db = connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
