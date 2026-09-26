"""Owner-scoped supplier, lot, draft, and dashboard rules."""
import re
import sqlite3
from math import sqrt
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from zoneinfo import ZoneInfo

from db import read_connection, transaction
from security import PASSWORDS, normalize_login, utc_now, verify_password

CODE_PATTERN = re.compile(r'^[A-Z0-9]{2,8}$')
UNSET = object()


class DomainError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def new_id():
    return uuid4().hex


def signup(display_name, login, password):
    name = display_name.strip()
    if not 2 <= len(name) <= 80:
        raise DomainError('Name must contain 2–80 characters.')
    if not 10 <= len(password) <= 128:
        raise DomainError('Password must contain 10–128 characters.')
    try:
        normalized = normalize_login(login)
    except ValueError as exc:
        raise DomainError(str(exc)) from exc
    user_id = new_id()
    try:
        with transaction() as db:
            db.execute('INSERT INTO users(id,login,display_name,password_hash,created_at) VALUES (?,?,?,?,?)',
                       (user_id, normalized, name, PASSWORDS.hash(password), utc_now()))
    except sqlite3.IntegrityError as exc:
        raise DomainError('This username or email is already in use.', 409) from exc
    return {'id': user_id, 'login': normalized, 'display_name': name, 'timezone': 'Asia/Jakarta'}


def login(identifier, password):
    try:
        normalized = normalize_login(identifier)
    except ValueError:
        raise DomainError('Incorrect username or password.', 401)
    with read_connection() as db:
        user = db.execute('SELECT * FROM users WHERE login=?', (normalized,)).fetchone()
    if not user or not verify_password(user['password_hash'], password):
        raise DomainError('Incorrect username or password.', 401)
    return {key: user[key] for key in ('id', 'login', 'display_name', 'timezone')}


def update_profile(owner_id, display_name):
    name = display_name.strip()
    if not 2 <= len(name) <= 80:
        raise DomainError('Name must contain 2–80 characters.')
    with transaction() as db:
        cursor = db.execute('UPDATE users SET display_name=? WHERE id=?', (name, owner_id))
        if not cursor.rowcount:
            raise DomainError('Account not found.', 404)
        user = db.execute('SELECT id,login,display_name,timezone FROM users WHERE id=?', (owner_id,)).fetchone()
    return dict(user)


def create_supplier(owner_id, name, code, contact='', notes=''):
    name, code, contact, notes = name.strip(), code.strip().upper(), contact.strip(), notes.strip()
    if not 2 <= len(name) <= 80:
        raise DomainError('Supplier name must contain 2–80 characters.')
    if not CODE_PATTERN.fullmatch(code):
        raise DomainError('Supplier code must contain 2–8 uppercase letters or digits.')
    if len(contact) > 120 or len(notes) > 1000:
        raise DomainError('Contact details or notes exceed the maximum length.')
    supplier_id, now = new_id(), utc_now()
    try:
        with transaction() as db:
            db.execute('''INSERT INTO suppliers(id,owner_id,name,code,contact,notes,created_at,updated_at)
                          VALUES (?,?,?,?,?,?,?,?)''', (supplier_id, owner_id, name, code, contact, notes, now, now))
    except sqlite3.IntegrityError as exc:
        raise DomainError('This supplier code is already in use.', 409) from exc
    return {'id': supplier_id, 'name': name, 'code': code, 'contact': contact, 'notes': notes, 'archived_at': None}


def list_suppliers(owner_id, include_archived=False):
    with read_connection() as db:
        sql = '''SELECT s.id,s.name,s.code,s.contact,s.notes,s.archived_at,
                        (SELECT COUNT(*) FROM lots l WHERE l.owner_id=s.owner_id AND l.supplier_id=s.id) AS lot_count
                 FROM suppliers s WHERE s.owner_id=?'''
        if not include_archived:
            sql += ' AND archived_at IS NULL'
        sql += ' ORDER BY name COLLATE NOCASE, code'
        return [dict(row) for row in db.execute(sql, (owner_id,))]


def update_supplier(owner_id, supplier_id, name, contact='', notes=''):
    name, contact, notes = name.strip(), contact.strip(), notes.strip()
    if not 2 <= len(name) <= 80 or len(contact) > 120 or len(notes) > 1000:
        raise DomainError('Check the supplier name, contact details, and notes.')
    with transaction() as db:
        cursor = db.execute('''UPDATE suppliers SET name=?,contact=?,notes=?,updated_at=?
            WHERE id=? AND owner_id=? AND archived_at IS NULL''',
            (name, contact, notes, utc_now(), supplier_id, owner_id))
        if not cursor.rowcount:
            raise DomainError('Active supplier not found.', 404)
    return next(item for item in list_suppliers(owner_id) if item['id'] == supplier_id)


def archive_supplier(owner_id, supplier_id, archived):
    with transaction() as db:
        row = db.execute('SELECT archived_at FROM suppliers WHERE id=? AND owner_id=?',
                         (supplier_id, owner_id)).fetchone()
        if not row:
            raise DomainError('Supplier not found.', 404)
        if bool(row['archived_at']) == archived:
            raise DomainError('Supplier status has changed. Refresh the list.', 409)
        cursor = db.execute('''UPDATE suppliers SET archived_at=?,updated_at=?
            WHERE id=? AND owner_id=? AND archived_at IS ?''',
            (utc_now() if archived else None, utc_now(), supplier_id, owner_id, row['archived_at']))
        if not cursor.rowcount:
            raise DomainError('Supplier not found or its status has changed.', 409)
    return {'id': supplier_id, 'archived': archived}


def delete_supplier(owner_id, supplier_id):
    with transaction() as db:
        supplier = db.execute('SELECT id FROM suppliers WHERE id=? AND owner_id=?',
                               (supplier_id, owner_id)).fetchone()
        if not supplier:
            raise DomainError('Supplier not found.', 404)
        linked = db.execute('SELECT COUNT(*) FROM lots WHERE owner_id=? AND supplier_id=?',
                            (owner_id, supplier_id)).fetchone()[0]
        if linked:
            raise DomainError('This supplier has linked lots. Archive the supplier to preserve lot history.', 409)
        db.execute('DELETE FROM suppliers WHERE id=? AND owner_id=?', (supplier_id, owner_id))
    return {'deleted': True}


def _issue_lot(db, owner_id, supplier_id, supplier_code, local_date):
    db.execute('''INSERT INTO lot_sequences(owner_id,supplier_id,local_date,last_issued)
                  VALUES (?,?,?,1) ON CONFLICT(owner_id,supplier_id,local_date)
                  DO UPDATE SET last_issued=last_issued+1''', (owner_id, supplier_id, local_date))
    number = db.execute('SELECT last_issued FROM lot_sequences WHERE owner_id=? AND supplier_id=? AND local_date=?',
                        (owner_id, supplier_id, local_date)).fetchone()[0]
    return number, f'{supplier_code}-{local_date.replace("-", "")}-{number:02d}'


def create_lot(owner_id, supplier_id=None):
    if not supplier_id:
        raise DomainError('Select a supplier before starting an analysis.')
    lot_id, draft_id, now = new_id(), new_id(), utc_now()
    with transaction() as db:
        supplier = db.execute('''SELECT id,code,name FROM suppliers WHERE id=? AND owner_id=? AND archived_at IS NULL''',
                              (supplier_id, owner_id)).fetchone()
        if not supplier:
            raise DomainError('Supplier is unavailable.', 404)
        tz = db.execute('SELECT timezone FROM users WHERE id=?', (owner_id,)).fetchone()['timezone']
        local_date = datetime.now(ZoneInfo(tz)).date().isoformat()
        number, human_id = _issue_lot(db, owner_id, supplier_id, supplier['code'], local_date)
        db.execute('''INSERT INTO lots(id,owner_id,supplier_id,human_id,issue_date,sequence,created_at)
                      VALUES (?,?,?,?,?,?,?)''', (lot_id, owner_id, supplier_id, human_id, local_date, number, now))
        db.execute('''INSERT INTO revisions(id,owner_id,lot_id,state,created_at,updated_at)
                      VALUES (?,?,?,?,?,?)''', (draft_id, owner_id, lot_id, 'draft', now, now))
    return get_draft(owner_id, draft_id)


def _draft_row(db, owner_id, draft_id):
    return db.execute('''SELECT r.*,l.human_id,l.version AS lot_version,l.supplier_id,
                               (SELECT COALESCE(MAX(done.revision_number),0)+1 FROM revisions done
                                WHERE done.lot_id=r.lot_id AND done.state='finalized') AS next_revision_number,
                               (SELECT base.revision_number FROM revisions base
                                WHERE base.id=r.base_revision_id) AS base_revision_number,
                               s.name AS supplier_name,s.code AS supplier_code,s.archived_at AS supplier_archived_at,
                               l.created_at AS lot_created_at
                        FROM revisions r JOIN lots l ON l.id=r.lot_id
                        LEFT JOIN suppliers s ON s.id=l.supplier_id
                        WHERE r.id=? AND r.owner_id=? AND r.state='draft' ''', (draft_id, owner_id)).fetchone()


def _draft_dict(row):
    if not row:
        raise DomainError('Draft not found.', 404)
    return {key: row[key] for key in ('id', 'lot_id', 'human_id', 'supplier_id', 'supplier_name', 'supplier_code',
                                      'supplier_archived_at',
                                      'weight_kg', 'notes', 'wizard_step', 'draft_version', 'input_version',
                                      'selected_run_id', 'base_revision_id', 'base_revision_number', 'next_revision_number',
                                      'created_at', 'updated_at')}


def get_draft(owner_id, draft_id):
    with read_connection() as db:
        return _draft_dict(_draft_row(db, owner_id, draft_id))


def list_drafts(owner_id):
    with read_connection() as db:
        return [_draft_dict(row) for row in db.execute('''SELECT r.*,l.human_id,l.supplier_id,
            (SELECT COALESCE(MAX(done.revision_number),0)+1 FROM revisions done
             WHERE done.lot_id=r.lot_id AND done.state='finalized') AS next_revision_number,
            (SELECT base.revision_number FROM revisions base
             WHERE base.id=r.base_revision_id) AS base_revision_number,
            s.name AS supplier_name,s.code AS supplier_code,s.archived_at AS supplier_archived_at FROM revisions r
            JOIN lots l ON l.id=r.lot_id LEFT JOIN suppliers s ON s.id=l.supplier_id
            WHERE r.owner_id=? AND r.state='draft' AND l.archived_at IS NULL
            ORDER BY r.updated_at DESC,r.id DESC''', (owner_id,))]


def begin_revision(owner_id, lot_id, expected_lot_version):
    """Create or reopen the one working copy for this lot; never change finalized evidence."""
    now = utc_now()
    with transaction() as db:
        lot = db.execute('''SELECT l.*,r.weight_kg,r.notes FROM lots l
            JOIN revisions r ON r.id=l.current_revision_id AND r.state='finalized'
            WHERE l.id=? AND l.owner_id=? AND l.archived_at IS NULL''', (lot_id, owner_id)).fetchone()
        if not lot:
            raise DomainError('Finalized lot not found.', 404)
        existing = db.execute("SELECT id FROM revisions WHERE lot_id=? AND owner_id=? AND state='draft'",
                              (lot_id, owner_id)).fetchone()
        if existing:
            return _draft_dict(_draft_row(db, owner_id, existing['id']))
        if lot['version'] != expected_lot_version:
            raise DomainError('The lot has changed. Refresh before starting a revision.', 409)
        draft_id = new_id()
        db.execute('''INSERT INTO revisions(id,owner_id,lot_id,state,base_revision_id,weight_kg,notes,
            wizard_step,draft_version,input_version,created_at,updated_at)
            VALUES (?,?,?,'draft',?,?,?,'sample',1,1,?,?)''',
            (draft_id, owner_id, lot_id, lot['current_revision_id'],lot['weight_kg'],lot['notes'],now,now))
        db.execute('''INSERT INTO revision_photos(revision_id,photo_id,precheck_id,sort_order,review_state)
            SELECT ?,photo_id,precheck_id,sort_order,review_state FROM revision_photos
            WHERE revision_id=? ORDER BY sort_order''', (draft_id,lot['current_revision_id']))
    return get_draft(owner_id, draft_id)


def list_revisions(owner_id, lot_id):
    with read_connection() as db:
        lot = db.execute('SELECT current_revision_id,version FROM lots WHERE id=? AND owner_id=?',
                         (lot_id,owner_id)).fetchone()
        if not lot:
            raise DomainError('Lot not found.', 404)
        rows = db.execute('''SELECT r.id,r.revision_number,r.finalized_at,r.supplier_name_snapshot,
            a.usable_count,a.fermented_count,a.poorly_count,a.excluded_count,
            COALESCE(g.manually_excluded,0) AS manually_excluded
            FROM revisions r JOIN analysis_runs a ON a.id=r.selected_run_id AND a.status='complete'
            LEFT JOIN revision_governance g ON g.revision_id=r.id
            WHERE r.lot_id=? AND r.owner_id=? AND r.state='finalized'
            ORDER BY r.revision_number DESC''', (lot_id,owner_id)).fetchall()
    return {'lot_version': lot['version'], 'current_revision_id': lot['current_revision_id'],
            'items': [dict(row) | {'current': row['id']==lot['current_revision_id']} for row in rows]}


def activate_revision(owner_id, lot_id, revision_id, expected_lot_version):
    with transaction() as db:
        lot = db.execute('SELECT version,current_revision_id FROM lots WHERE id=? AND owner_id=?',
                         (lot_id,owner_id)).fetchone()
        if not lot:
            raise DomainError('Lot not found.', 404)
        revision = db.execute("SELECT id FROM revisions WHERE id=? AND lot_id=? AND owner_id=? AND state='finalized'",
                              (revision_id,lot_id,owner_id)).fetchone()
        if not revision:
            raise DomainError('Finalized revision not found.', 404)
        if lot['version'] != expected_lot_version:
            raise DomainError('The current revision has changed. Refresh to see the latest version.', 409)
        if lot['current_revision_id'] != revision_id:
            db.execute('UPDATE lots SET current_revision_id=?,version=version+1 WHERE id=? AND owner_id=?',
                       (revision_id,lot_id,owner_id))
    return list_revisions(owner_id,lot_id)


def delete_draft(owner_id, draft_id):
    """Remove one unfinished revision and only assets no other revision references."""
    with transaction() as db:
        draft = _draft_row(db, owner_id, draft_id)
        if not draft:
            raise DomainError('Draft not found.', 404)
        photo_ids = [row['photo_id'] for row in db.execute(
            'SELECT photo_id FROM revision_photos WHERE revision_id=?', (draft_id,))]
        run_ids = [row['id'] for row in db.execute(
            'SELECT id FROM analysis_runs WHERE revision_id=? AND owner_id=?', (draft_id, owner_id))]
        for run_id in run_ids:
            db.execute("DELETE FROM processing_jobs WHERE owner_id=? AND kind='classify' AND target_id=?",
                       (owner_id, run_id))
        db.execute('DELETE FROM analysis_runs WHERE revision_id=? AND owner_id=?', (draft_id, owner_id))
        db.execute('DELETE FROM revision_photos WHERE revision_id=?', (draft_id,))
        db.execute('DELETE FROM revisions WHERE id=? AND owner_id=? AND state=\'draft\'', (draft_id, owner_id))
        remaining = db.execute('SELECT 1 FROM revisions WHERE lot_id=? LIMIT 1', (draft['lot_id'],)).fetchone()
        if not remaining:
            db.execute('DELETE FROM lots WHERE id=? AND owner_id=? AND current_revision_id IS NULL',
                       (draft['lot_id'], owner_id))
        orphaned = []
        for photo_id in photo_ids:
            referenced = db.execute('SELECT 1 FROM revision_photos WHERE photo_id=? LIMIT 1', (photo_id,)).fetchone()
            if referenced:
                continue
            prechecks = [row['id'] for row in db.execute('SELECT id FROM prechecks WHERE photo_id=?', (photo_id,))]
            for precheck_id in prechecks:
                db.execute("DELETE FROM processing_jobs WHERE owner_id=? AND kind='precheck' AND target_id=?",
                           (owner_id, precheck_id))
            db.execute('DELETE FROM prechecks WHERE photo_id=?', (photo_id,))
            db.execute('DELETE FROM photos WHERE id=? AND owner_id=?', (photo_id, owner_id))
            orphaned.append(photo_id)
    return {'deleted': True, 'lot_id': draft['lot_id'], 'orphaned_photo_ids': orphaned,
            'run_ids': run_ids}


def finalized_receipt(owner_id, revision_id):
    with read_connection() as db:
        row = db.execute('''SELECT r.lot_id,l.human_id,r.id AS revision_id,r.revision_number,
            r.supplier_name_snapshot AS supplier_name,r.finalized_at FROM revisions r
            JOIN lots l ON l.id=r.lot_id AND l.owner_id=r.owner_id
            WHERE r.id=? AND r.owner_id=? AND r.state='finalized' ''', (revision_id, owner_id)).fetchone()
    return dict(row) if row else None


def finalize_draft(owner_id, draft_id, expected_version):
    now = utc_now()
    with transaction() as db:
        revision = db.execute("SELECT * FROM revisions WHERE id=? AND owner_id=? AND state='draft'",
                              (draft_id, owner_id)).fetchone()
        if not revision:
            finalized = db.execute("SELECT id FROM revisions WHERE id=? AND owner_id=? AND state='finalized'",
                                   (draft_id, owner_id)).fetchone()
            if finalized:
                return finalized_receipt(owner_id, draft_id)
            raise DomainError('Draft not found.', 404)
        if revision['draft_version'] != expected_version:
            raise DomainError('The draft was changed in another tab. Refresh before saving.', 409)
        run = db.execute("SELECT * FROM analysis_runs WHERE id=? AND revision_id=? AND owner_id=?",
                         (revision['selected_run_id'], draft_id, owner_id)).fetchone()
        if not run or run['status'] != 'complete' or run['input_version'] != revision['input_version']:
            raise DomainError('Results are not ready or no longer match the sample.', 409)
        if not run['usable_count'] or run['fermented_count'] + run['poorly_count'] != run['usable_count']:
            raise DomainError('Result counts do not match the analyzed beans.', 409)
        lot = db.execute('SELECT * FROM lots WHERE id=? AND owner_id=?', (revision['lot_id'], owner_id)).fetchone()
        if not lot:
            raise DomainError('Lot not found.', 404)
        if revision['base_revision_id'] and lot['current_revision_id'] != revision['base_revision_id']:
            raise DomainError('The current revision has changed since this draft was created. Select its base revision again before saving.', 409)
        require_lot_supplier(db, owner_id, lot['id'])
        number = db.execute('SELECT COALESCE(MAX(revision_number),0)+1 FROM revisions WHERE lot_id=?',
                            (revision['lot_id'],)).fetchone()[0]
        supplier = db.execute('SELECT name FROM suppliers WHERE id=? AND owner_id=?',
                              (lot['supplier_id'], owner_id)).fetchone() if lot['supplier_id'] else None
        tz = db.execute('SELECT timezone FROM users WHERE id=?', (owner_id,)).fetchone()['timezone']
        local_date = datetime.now(ZoneInfo(tz)).date().isoformat()
        db.execute('''UPDATE revisions SET state='finalized',revision_number=?,supplier_name_snapshot=?,
            finalized_at=?,updated_at=? WHERE id=? AND owner_id=? AND state='draft' ''',
            (number, supplier['name'] if supplier else None, now, now, draft_id, owner_id))
        db.execute('''UPDATE lots SET current_revision_id=?,
            first_finalized_at=COALESCE(first_finalized_at,?),
            first_finalized_date=COALESCE(first_finalized_date,?),version=version+1
            WHERE id=? AND owner_id=?''', (draft_id, now, local_date, revision['lot_id'], owner_id))
        return {'lot_id': revision['lot_id'], 'human_id': lot['human_id'],
                'revision_id': draft_id, 'revision_number': number,
                'supplier_name': supplier['name'] if supplier else None,
                'finalized_at': now}


def list_finalized_lots(owner_id):
    with read_connection() as db:
        return _current_finalized_lots(db, owner_id, include_archived=False)


def _weight_text(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise DomainError('Invalid lot weight.') from exc
    if not amount.is_finite() or amount <= 0 or amount > Decimal('100000000') or amount.as_tuple().exponent < -3:
        raise DomainError('Weight must be positive, with up to three decimal places.')
    return format(amount.normalize(), 'f')


def update_draft(owner_id, draft_id, expected_version, weight_kg, notes, wizard_step, supplier_id=UNSET):
    if wizard_step not in ('lot', 'sample', 'result'):
        raise DomainError('Unknown analysis step.')
    if len(notes) > 1000:
        raise DomainError('Notes exceed the maximum length.')
    weight = _weight_text(weight_kg)
    now = utc_now()
    with transaction() as db:
        row = _draft_row(db, owner_id, draft_id)
        if not row:
            raise DomainError('Draft not found.', 404)
        if row['draft_version'] != expected_version:
            raise DomainError('The draft was changed in another tab. Refresh to see the latest version.', 409)
        if supplier_id is not UNSET and not supplier_id:
            raise DomainError('A supplier is required and cannot be cleared.')
        if supplier_id is not UNSET and supplier_id != row['supplier_id']:
            supplier = db.execute('SELECT id,code FROM suppliers WHERE owner_id=? AND id=? AND archived_at IS NULL',
                                  (owner_id, supplier_id)).fetchone()
            if not supplier:
                raise DomainError('Supplier is unavailable.', 404)
            if row['base_revision_id']:
                raise DomainError('The supplier of a finalized lot cannot be changed.', 409)
            tz = db.execute('SELECT timezone FROM users WHERE id=?', (owner_id,)).fetchone()['timezone']
            local_date = datetime.now(ZoneInfo(tz)).date().isoformat()
            number, human_id = _issue_lot(db, owner_id, supplier_id, supplier['code'], local_date)
            db.execute('''UPDATE lots SET supplier_id=?,human_id=?,issue_date=?,sequence=?,version=version+1
                          WHERE id=? AND owner_id=?''', (supplier_id, human_id, local_date, number, row['lot_id'], owner_id))
        if wizard_step != 'lot':
            require_lot_supplier(db, owner_id, row['lot_id'])
        db.execute('''UPDATE revisions SET weight_kg=?,notes=?,wizard_step=?,draft_version=draft_version+1,updated_at=?
                      WHERE id=? AND owner_id=? AND state='draft' ''',
                   (weight, notes.strip(), wizard_step, now, draft_id, owner_id))
    return get_draft(owner_id, draft_id)


def require_lot_supplier(db, owner_id, lot_id):
    """Archived assignments remain valid for existing drafts; new selection must be active."""
    lot = db.execute('''SELECT l.supplier_id FROM lots l
        JOIN suppliers s ON s.id=l.supplier_id AND s.owner_id=l.owner_id
        WHERE l.id=? AND l.owner_id=?''', (lot_id, owner_id)).fetchone()
    if not lot:
        raise DomainError('Select a supplier in Lot details before continuing.', 409)


def require_draft_supplier(db, owner_id, draft_id):
    row = db.execute("SELECT lot_id FROM revisions WHERE id=? AND owner_id=? AND state='draft'",
                     (draft_id, owner_id)).fetchone()
    if not row:
        raise DomainError('Draft not found.', 404)
    require_lot_supplier(db, owner_id, row['lot_id'])


def get_finalized_lot(owner_id, lot_id):
    with read_connection() as db:
        row = db.execute('''SELECT l.id AS lot_id,l.human_id,l.supplier_id,l.first_finalized_at,
            r.id AS id,r.revision_number,r.weight_kg,r.notes,r.finalized_at,r.selected_run_id,
            l.version AS lot_version,
            r.supplier_name_snapshot AS supplier_name,s.code AS supplier_code
            FROM lots l JOIN revisions r ON r.id=l.current_revision_id AND r.lot_id=l.id
            LEFT JOIN suppliers s ON s.id=l.supplier_id AND s.owner_id=l.owner_id
            WHERE l.id=? AND l.owner_id=? AND r.owner_id=? AND r.state='finalized' ''',
            (lot_id, owner_id, owner_id)).fetchone()
    if not row:
        raise DomainError('Finalized lot not found.', 404)
    return dict(row)


def get_finalized_revision(owner_id, lot_id, revision_id):
    with read_connection() as db:
        row = db.execute('''SELECT l.id AS lot_id,l.human_id,l.supplier_id,l.first_finalized_at,
            l.current_revision_id,l.version AS lot_version,r.id,r.revision_number,r.weight_kg,
            r.notes,r.finalized_at,r.selected_run_id,r.supplier_name_snapshot AS supplier_name,
            s.code AS supplier_code
            FROM lots l JOIN revisions r ON r.lot_id=l.id AND r.state='finalized'
            LEFT JOIN suppliers s ON s.id=l.supplier_id AND s.owner_id=l.owner_id
            WHERE l.id=? AND l.owner_id=? AND r.id=? AND r.owner_id=?''',
            (lot_id,owner_id,revision_id,owner_id)).fetchone()
    if not row:
        raise DomainError('Finalized revision not found.',404)
    return dict(row)


def sample_band(usable):
    if usable < 50:
        return {'id': 'under50', 'label': 'Very limited',
                'description': 'Samples below 50 beans are excluded from summary statistics.'}
    if usable < 100:
        return {'id': '50to99', 'label': 'Small sample',
                'description': 'Results are available, but the sample size is small.'}
    if usable < 300:
        return {'id': '100to299', 'label': 'Indicative',
                'description': 'The sample is approaching the 300-bean reference; representativeness still matters.'}
    return {'id': '300plus', 'label': 'Meets sample-size reference',
            'description': 'The 300-bean reference is met; representativeness still matters.'}


def _is_statistically_eligible(item):
    """Only the finalized current revision's selected run can enter quality statistics."""
    return item['usable_count'] >= 50 and not item['manually_excluded']


def _current_finalized_lots(db, owner_id, *, include_archived=True, supplier_id=None, start=None):
    """One current finalized revision per owned lot; shared by History and quality summaries."""
    rows = db.execute('''SELECT l.id AS lot_id,l.human_id,l.supplier_id,l.archived_at,
        l.first_finalized_at,l.first_finalized_date,
        COALESCE(r.supplier_name_snapshot,s.name) AS supplier_name,s.code AS supplier_code,
        r.id AS revision_id,r.revision_number,r.weight_kg,r.notes,
        a.usable_count,a.fermented_count,a.poorly_count,a.excluded_count,a.photo_count,
        COALESCE(g.manually_excluded,0) AS manually_excluded
        FROM lots l JOIN suppliers s ON s.id=l.supplier_id AND s.owner_id=l.owner_id
        JOIN revisions r ON r.id=l.current_revision_id AND r.lot_id=l.id AND r.state='finalized'
        JOIN analysis_runs a ON a.id=r.selected_run_id AND a.status='complete'
        LEFT JOIN revision_governance g ON g.revision_id=r.id
        WHERE l.owner_id=? AND (? OR l.archived_at IS NULL)
          AND (? IS NULL OR l.supplier_id=?)
          AND (? IS NULL OR l.first_finalized_date>=?)
        ORDER BY l.first_finalized_at DESC,l.id DESC''',
        (owner_id, int(include_archived), supplier_id, supplier_id, start, start)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item['percent'] = 100 * item['fermented_count'] / item['usable_count'] if item['usable_count'] else None
        item['sample_band'] = sample_band(item['usable_count'])
        item['eligible'] = _is_statistically_eligible(item)
        items.append(item)
    return items


def supplier_performance(owner_id, supplier_id):
    with read_connection() as db:
        supplier = db.execute('''SELECT id,name,code,contact,notes,created_at,archived_at
            FROM suppliers WHERE id=? AND owner_id=?''', (supplier_id, owner_id)).fetchone()
        if not supplier:
            raise DomainError('Supplier not found.', 404)
        lots = _current_finalized_lots(db, owner_id, supplier_id=supplier_id)
    eligible = [item for item in lots if item['eligible']]
    values = [item['percent'] for item in eligible]
    mean = sum(values) / len(values) if values else None
    weights = [Decimal(item['weight_kg']) for item in lots if item['weight_kg'] is not None]
    return {
        'supplier': dict(supplier), 'total_lots': len(lots), 'eligible_lots': len(eligible),
        'mean_fermented': mean,
        'min_fermented': min(values) if values else None,
        'max_fermented': max(values) if values else None,
        'stddev_points': sqrt(sum((value - mean) ** 2 for value in values) / len(values)) if values else None,
        'sample_300_count': sum(item['usable_count'] >= 300 for item in lots),
        'excluded_lots': len(lots) - len(eligible),
        'weight_kg': format(sum(weights, Decimal('0')), 'f'), 'weight_count': len(weights),
        'trend': list(reversed(eligible)), 'history': lots,
    }


def _period_start(period, tz):
    today = datetime.now(ZoneInfo(tz)).date()
    if period == '7d':
        return today - timedelta(days=6)
    if period == '30d':
        return today - timedelta(days=29)
    if period == '3m':
        year, month = today.year, today.month - 3
        while month <= 0:
            year -= 1
            month += 12
        from calendar import monthrange
        return today.replace(year=year, month=month, day=min(today.day, monthrange(year, month)[1]))
    if period == 'all':
        return None
    raise DomainError('Unknown reporting period.')


def dashboard(owner_id, period='30d'):
    with read_connection() as db:
        user = db.execute('SELECT timezone FROM users WHERE id=?', (owner_id,)).fetchone()
        start = _period_start(period, user['timezone'])
        lots = _current_finalized_lots(db, owner_id, start=start.isoformat() if start else None)
        draft_count = db.execute('''SELECT count(*) FROM revisions r JOIN lots l ON l.id=r.lot_id
            WHERE r.owner_id=? AND r.state='draft' AND l.archived_at IS NULL''', (owner_id,)).fetchone()[0]
        active_suppliers = db.execute('SELECT count(*) FROM suppliers WHERE owner_id=? AND archived_at IS NULL', (owner_id,)).fetchone()[0]
    eligible = [item for item in lots if item['eligible']]
    weights = [Decimal(item['weight_kg']) for item in lots if item['weight_kg'] is not None]
    return {
        'period': period, 'lot_count': len(lots), 'eligible_count': len(eligible),
        'mean_fermented': sum(item['percent'] for item in eligible) / len(eligible) if eligible else None,
        'weight_kg': format(sum(weights, Decimal('0')), 'f'), 'weight_count': len(weights),
        'sample_bands': {band: sum(item['sample_band']['id'] == band for item in lots)
                         for band in ('under50', '50to99', '100to299', '300plus')},
        'trend': list(reversed(eligible)), 'recent': lots[:3],
        'attention': {
            'drafts': draft_count,
            'low_sample': sum(item['usable_count'] < 50 for item in lots),
            'high_exclusion': sum(item['excluded_count'] / max(1, item['usable_count'] + item['excluded_count']) > .25 for item in lots),
        },
        'active_supplier_count': active_suppliers,
    }
