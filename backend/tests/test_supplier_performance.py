"""Supplier performance uses the same current-revision population as Home."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import db  # noqa: E402
import domain  # noqa: E402


class SupplierPerformance(unittest.TestCase):
    def test_current_eligible_lots_and_owner_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            with patch.object(db, 'DATA_DIR', path), patch.object(db, 'DB_PATH', path / 'kakaolens.sqlite3'):
                db.migrate()
                with db.transaction() as conn:
                    for owner in ('alice', 'bob'):
                        conn.execute('''INSERT INTO users(id,login,display_name,password_hash,created_at)
                            VALUES (?,?,?,?,?)''', (owner, owner, owner, 'unused', '2026-09-26T00:00:00Z'))
                    conn.execute('''INSERT INTO suppliers(id,owner_id,name,code,created_at,updated_at)
                        VALUES ('supplier','alice','Cocoa Farm','FARM','2026-09-01','2026-09-01')''')
                    conn.execute('''INSERT INTO suppliers(id,owner_id,name,code,created_at,updated_at)
                        VALUES ('other','alice','Other Farm','OTHR','2026-09-01','2026-09-01')''')
                    def add_lot(number, supplier, revisions, current, archived=False, excluded=False):
                        lot = f'lot{number}'
                        conn.execute('''INSERT INTO lots(id,owner_id,supplier_id,human_id,issue_date,sequence,
                            first_finalized_at,first_finalized_date,archived_at,created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?)''',
                            (lot, 'alice', supplier, f'FARM-20260926-{number:02d}', '2026-09-26', number,
                             '2026-09-26T10:00:00Z', '2026-09-26', '2026-09-27' if archived else None,
                             '2026-09-26T09:00:00Z'))
                        for revision_number, usable, fermented in revisions:
                            revision = f'{lot}r{revision_number}'
                            run = f'{revision}run'
                            conn.execute('''INSERT INTO revisions(id,owner_id,lot_id,state,revision_number,
                                selected_run_id,created_at,updated_at,finalized_at)
                                VALUES (?,? ,?,'finalized',?,?,?,?,?)''',
                                (revision, 'alice', lot, revision_number, run, '2026-09-26T09:00:00Z',
                                 '2026-09-26T10:00:00Z', '2026-09-26T10:00:00Z'))
                            conn.execute('''INSERT INTO analysis_runs(id,owner_id,revision_id,input_version,
                                input_sha256,status,usable_count,fermented_count,poorly_count,excluded_count,
                                photo_count,created_at,completed_at)
                                VALUES (?,?,?,1,'hash','complete',?,?,?,?,1,?,?)''',
                                (run, 'alice', revision, usable, fermented, usable-fermented, 0,
                                 '2026-09-26T09:30:00Z', '2026-09-26T10:00:00Z'))
                            if revision_number == current and excluded:
                                conn.execute('''INSERT INTO revision_governance(revision_id,manually_excluded,updated_at)
                                    VALUES (?,1,'2026-09-26T10:00:00Z')''', (revision,))
                        conn.execute('UPDATE lots SET current_revision_id=? WHERE id=?',
                                     (f'{lot}r{current}', lot))
                    add_lot(1, 'supplier', [(1, 50, 50), (2, 50, 40)], 2, archived=True)
                    add_lot(2, 'supplier', [(1, 100, 60)], 1)
                    add_lot(3, 'supplier', [(1, 49, 49)], 1)
                    add_lot(4, 'supplier', [(1, 100, 100)], 1, excluded=True)
                    add_lot(5, 'other', [(1, 100, 0)], 1)
                result = domain.supplier_performance('alice', 'supplier')
                self.assertEqual((result['total_lots'], result['eligible_lots'], result['excluded_lots']), (4, 2, 2))
                self.assertEqual((result['mean_fermented'], result['min_fermented'], result['max_fermented']), (70, 60, 80))
                self.assertEqual(result['stddev_points'], 10)
                self.assertEqual({item['lot_id'] for item in result['trend']}, {'lot1', 'lot2'})
                self.assertEqual(len(result['history']), 4)
                self.assertEqual(domain.dashboard('alice', 'all')['mean_fermented'], 140 / 3)
                with self.assertRaises(domain.DomainError) as denied:
                    domain.supplier_performance('bob', 'supplier')
                self.assertEqual(denied.exception.status, 404)


if __name__ == '__main__':
    unittest.main()
