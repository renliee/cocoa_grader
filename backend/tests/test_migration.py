"""Existing supplier-bound drafts survive the optional-supplier migration."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MigrationUpgrade(unittest.TestCase):
    def test_existing_draft_survives(self):
        parent = ROOT / 'data'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temp:
            data_dir = Path(temp).resolve()
            self.assertTrue(data_dir.is_relative_to(ROOT.resolve()))
            path = data_dir / 'kakaolens.sqlite3'
            db = sqlite3.connect(path)
            try:
                db.execute('PRAGMA foreign_keys=ON')
                db.executescript((ROOT / 'backend/migrations/001_foundation.sql').read_text(encoding='utf-8'))
                db.execute('CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
                db.execute("INSERT INTO schema_migrations(version) VALUES ('001_foundation')")
                db.execute("INSERT INTO users(id,login,display_name,password_hash,created_at) VALUES ('u','old','Old','hash','2026-09-01')")
                db.execute("INSERT INTO suppliers(id,owner_id,name,code,created_at,updated_at) VALUES ('s','u','Old Supplier','OLD','2026-09-01','2026-09-01')")
                db.execute("INSERT INTO lots(id,owner_id,supplier_id,human_id,issue_date,sequence,created_at) VALUES ('l','u','s','OLD-20260901-01','2026-09-01',1,'2026-09-01')")
                db.execute("INSERT INTO revisions(id,owner_id,lot_id,state,created_at,updated_at) VALUES ('r','u','l','draft','2026-09-01','2026-09-01')")
                db.commit()
            finally:
                db.close()
            env = dict(os.environ, KAKAO_DATA_DIR=str(data_dir))
            migrated = subprocess.run([sys.executable, '-c', 'import db; db.migrate()'], cwd=str(ROOT / 'backend'),
                                      env=env, capture_output=True, text=True)
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            db = sqlite3.connect(path)
            try:
                self.assertEqual(db.execute('SELECT human_id FROM lots WHERE id=\'l\'').fetchone()[0],
                                 'OLD-20260901-01')
                self.assertEqual(db.execute('SELECT lot_id FROM revisions WHERE id=\'r\'').fetchone()[0], 'l')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='reports'").fetchone()[0], 1)
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("INSERT INTO lots(id,owner_id,supplier_id,human_id,issue_date,sequence,created_at) VALUES ('anon','u',NULL,'QC-UNASSIGNED-20260901-01','2026-09-01',1,'2026-09-01')")
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("UPDATE lots SET supplier_id=NULL WHERE id='l'")
                self.assertEqual(db.execute("SELECT supplier_id FROM lots WHERE id='l'").fetchone()[0], 's')
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
