"""Authoritative uploaded-photo prechecks and draft photo review."""
import hashlib
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from core import classify, config, grade, segment
from core.precheck import render_precheck
from db import read_connection, transaction
from domain import DomainError, sample_band, require_draft_supplier
from presentation import result_copy, precheck_warnings
from security import utc_now
from storage import delete_photo_assets, photo_key, read_asset, write_asset

log = logging.getLogger('kakaolens.workflow')
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_PHOTOS = 50
_executor = None
_classifier = None


def _id():
    return uuid4().hex


def start_worker(classifier=None):
    global _executor, _classifier
    _classifier = classifier
    _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='kakao-cv')
    with transaction() as db:
        pending_prechecks = [row['target_id'] for row in db.execute(
            "SELECT target_id FROM processing_jobs WHERE kind='precheck' AND state IN ('queued','running')")]
        pending_runs = [row['target_id'] for row in db.execute(
            "SELECT target_id FROM processing_jobs WHERE kind='classify' AND state IN ('queued','running')")]
        db.execute("UPDATE processing_jobs SET state='queued' WHERE kind='precheck' AND state='running'")
        db.execute("UPDATE processing_jobs SET state='queued' WHERE kind='classify' AND state='running'")
        db.execute("UPDATE prechecks SET status='queued' WHERE status='processing'")
        db.execute("UPDATE analysis_runs SET status='queued' WHERE status='processing'")
    for target in dict.fromkeys(pending_prechecks):
        _executor.submit(_run_precheck, target)
    if _classifier is not None:
        for target in dict.fromkeys(pending_runs):
            _executor.submit(_run_classification, target)


def stop_worker():
    global _executor, _classifier
    if _executor:
        _executor.shutdown(wait=True)
        _executor = None
    _classifier = None


def _schedule(precheck_id):
    if _executor is None:
        raise RuntimeError('Precheck worker is not running')
    _executor.submit(_run_precheck, precheck_id)


def _validate_photo(raw):
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise DomainError('The photo must not be empty and must be no larger than 10 MB.')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            fmt = image.format
            width, height = image.size
            exif_orientation = int(image.getexif().get(274, 1))
            if fmt not in ('JPEG', 'PNG'):
                raise DomainError('Use a JPEG or PNG photo.')
            if width < 100 or height < 100 or width * height > MAX_IMAGE_PIXELS:
                raise DomainError('Photo dimensions exceed the supported limits.')
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise DomainError('Unable to read this photo. Use an intact JPEG or PNG file.') from exc
    return fmt, width, height, exif_orientation


def upload_photo(owner_id, draft_id, filename, raw, upload_key):
    if not upload_key or len(upload_key) > 80:
        raise DomainError('Invalid upload key.')
    fmt, width, height, exif_orientation = _validate_photo(raw)
    digest = hashlib.sha256(raw).hexdigest()
    with read_connection() as db:
        require_draft_supplier(db, owner_id, draft_id)
        existing = db.execute('''SELECT p.id,p.sha256 FROM revision_photos rp
            JOIN revisions r ON r.id=rp.revision_id JOIN photos p ON p.id=rp.photo_id
            WHERE rp.revision_id=? AND rp.upload_key=? AND r.owner_id=? AND r.state='draft' ''',
            (draft_id, upload_key, owner_id)).fetchone()
    if existing:
        if existing['sha256'] != digest:
            raise DomainError('This upload key has already been used for another photo.', 409)
        return get_photo(owner_id, draft_id, existing['id'])
    photo_id, precheck_id, job_id = _id(), _id(), _id()
    ext = 'jpg' if fmt == 'JPEG' else 'png'
    original_key = photo_key(owner_id, photo_id, f'original.{ext}')
    write_asset(original_key, raw)
    safe_name = filename.replace('\\', '/').split('/')[-1][:120] or f'foto.{ext}'
    try:
        with transaction() as db:
            require_draft_supplier(db, owner_id, draft_id)
            revision = db.execute('SELECT lot_id FROM revisions WHERE id=? AND owner_id=? AND state=\'draft\'',
                                  (draft_id, owner_id)).fetchone()
            if not revision:
                raise DomainError('Draft not found.', 404)
            count = db.execute('SELECT count(*) FROM revision_photos WHERE revision_id=?', (draft_id,)).fetchone()[0]
            if count >= MAX_PHOTOS:
                raise DomainError(f'A maximum of {MAX_PHOTOS} photos is allowed per analysis.')
            now = utc_now()
            db.execute('''INSERT INTO photos(id,owner_id,filename,sha256,original_key,width,height,
                        created_at,media_type,byte_size,source_width,source_height,exif_orientation)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (photo_id, owner_id, safe_name, digest, original_key, width, height,
                        now, f'image/{"jpeg" if fmt == "JPEG" else "png"}', len(raw),
                        width, height, exif_orientation))
            db.execute('''INSERT INTO prechecks(id,owner_id,photo_id,status,created_at)
                          VALUES (?,?,?,?,?)''', (precheck_id, owner_id, photo_id, 'queued', now))
            db.execute('''INSERT INTO revision_photos(revision_id,photo_id,precheck_id,sort_order,review_state,upload_key)
                          VALUES (?,?,?,?,?,?)''', (draft_id, photo_id, precheck_id, count, 'included', upload_key))
            db.execute('''INSERT INTO processing_jobs(id,owner_id,kind,target_id,state,created_at)
                          VALUES (?,?,?,?,?,?)''', (job_id, owner_id, 'precheck', precheck_id, 'queued', now))
            db.execute('''UPDATE revisions SET wizard_step='sample',input_version=input_version+1,
                          draft_version=draft_version+1,selected_run_id=NULL,updated_at=? WHERE id=?''',
                       (now, draft_id))
    except Exception:
        delete_photo_assets(owner_id, photo_id)
        raise
    _schedule(precheck_id)
    return get_photo(owner_id, draft_id, photo_id)


def replace_photo(owner_id, draft_id, old_photo_id, filename, raw, upload_key):
    """Replace one draft photo atomically while preserving its carousel position."""
    if not upload_key or len(upload_key) > 80:
        raise DomainError('Invalid upload key.')
    fmt, width, height, exif_orientation = _validate_photo(raw)
    digest = hashlib.sha256(raw).hexdigest()
    photo_id, precheck_id, job_id = _id(), _id(), _id()
    ext = 'jpg' if fmt == 'JPEG' else 'png'
    original_key = photo_key(owner_id, photo_id, f'original.{ext}')
    write_asset(original_key, raw)
    safe_name = filename.replace('\\', '/').split('/')[-1][:120] or f'foto.{ext}'
    try:
        with transaction() as db:
            require_draft_supplier(db, owner_id, draft_id)
            old = db.execute('''SELECT rp.precheck_id,rp.sort_order FROM revision_photos rp
                JOIN revisions r ON r.id=rp.revision_id
                WHERE rp.revision_id=? AND rp.photo_id=? AND r.owner_id=? AND r.state='draft' ''',
                (draft_id, old_photo_id, owner_id)).fetchone()
            if not old:
                raise DomainError('Photo or draft not found.', 404)
            now = utc_now()
            db.execute('''INSERT INTO photos(id,owner_id,filename,sha256,original_key,width,height,
                        created_at,media_type,byte_size,source_width,source_height,exif_orientation)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (photo_id, owner_id, safe_name, digest, original_key, width, height,
                        now, f'image/{"jpeg" if fmt == "JPEG" else "png"}', len(raw),
                        width, height, exif_orientation))
            db.execute('INSERT INTO prechecks(id,owner_id,photo_id,status,created_at) VALUES (?,?,?,?,?)',
                       (precheck_id, owner_id, photo_id, 'queued', now))
            db.execute('''UPDATE revision_photos SET photo_id=?,precheck_id=?,review_state='included',upload_key=?
                WHERE revision_id=? AND photo_id=?''',
                       (photo_id, precheck_id, upload_key, draft_id, old_photo_id))
            orphaned = not db.execute('SELECT 1 FROM revision_photos WHERE photo_id=? LIMIT 1',
                                      (old_photo_id,)).fetchone()
            if orphaned:
                db.execute("DELETE FROM processing_jobs WHERE owner_id=? AND kind='precheck' AND target_id=?",
                           (owner_id, old['precheck_id']))
                db.execute('DELETE FROM prechecks WHERE id=? AND owner_id=?', (old['precheck_id'], owner_id))
                db.execute('DELETE FROM photos WHERE id=? AND owner_id=?', (old_photo_id, owner_id))
            db.execute('INSERT INTO processing_jobs(id,owner_id,kind,target_id,state,created_at) VALUES (?,?,?,?,?,?)',
                       (job_id, owner_id, 'precheck', precheck_id, 'queued', now))
            db.execute('''UPDATE revisions SET input_version=input_version+1,draft_version=draft_version+1,
                selected_run_id=NULL,updated_at=? WHERE id=?''', (now, draft_id))
    except Exception:
        delete_photo_assets(owner_id, photo_id)
        raise
    if orphaned:
        delete_photo_assets(owner_id, old_photo_id)
    _schedule(precheck_id)
    return get_photo(owner_id, draft_id, photo_id)


def delete_draft_photo(owner_id, draft_id, photo_id):
    """Remove one photo from an unfinished analysis and leave all other records intact."""
    with transaction() as db:
        row = db.execute('''SELECT rp.precheck_id FROM revision_photos rp
            JOIN revisions r ON r.id=rp.revision_id
            WHERE rp.revision_id=? AND rp.photo_id=? AND r.owner_id=? AND r.state='draft' ''',
            (draft_id, photo_id, owner_id)).fetchone()
        if not row:
            raise DomainError('Photo or draft not found.', 404)
        db.execute('DELETE FROM revision_photos WHERE revision_id=? AND photo_id=?', (draft_id, photo_id))
        orphaned = not db.execute('SELECT 1 FROM revision_photos WHERE photo_id=? LIMIT 1',
                                  (photo_id,)).fetchone()
        if orphaned:
            db.execute("DELETE FROM processing_jobs WHERE owner_id=? AND kind='precheck' AND target_id=?",
                       (owner_id, row['precheck_id']))
            db.execute('DELETE FROM prechecks WHERE id=? AND owner_id=?', (row['precheck_id'], owner_id))
            db.execute('DELETE FROM photos WHERE id=? AND owner_id=?', (photo_id, owner_id))
        db.execute('''WITH ordered AS (
            SELECT photo_id,ROW_NUMBER() OVER (ORDER BY sort_order,photo_id)-1 AS new_order
            FROM revision_photos WHERE revision_id=?
        ) UPDATE revision_photos SET sort_order=(SELECT new_order FROM ordered WHERE ordered.photo_id=revision_photos.photo_id)
            WHERE revision_id=?''', (draft_id, draft_id))
        db.execute('''UPDATE revisions SET input_version=input_version+1,draft_version=draft_version+1,
            selected_run_id=NULL,updated_at=? WHERE id=?''', (utc_now(), draft_id))
    if orphaned:
        delete_photo_assets(owner_id, photo_id)
    return {'deleted': True}


def clear_draft_photos(owner_id, draft_id, expected_input_version):
    """Detach the whole draft sample atomically and clean only unreferenced photo assets."""
    orphaned = []
    with transaction() as db:
        revision = db.execute("SELECT input_version FROM revisions WHERE id=? AND owner_id=? AND state='draft'",
                              (draft_id, owner_id)).fetchone()
        if not revision:
            raise DomainError('Draft not found.', 404)
        if revision['input_version'] != expected_input_version:
            raise DomainError('The sample has changed. Refresh before deleting all photos.', 409)
        photo_ids = [row[0] for row in db.execute('SELECT photo_id FROM revision_photos WHERE revision_id=?', (draft_id,))]
        db.execute('DELETE FROM revision_photos WHERE revision_id=?', (draft_id,))
        for photo_id in photo_ids:
            if db.execute('SELECT 1 FROM revision_photos WHERE photo_id=?', (photo_id,)).fetchone():
                continue
            prechecks = list(db.execute('SELECT id FROM prechecks WHERE photo_id=? AND owner_id=?', (photo_id, owner_id)))
            for precheck in prechecks:
                db.execute("DELETE FROM processing_jobs WHERE owner_id=? AND kind='precheck' AND target_id=?", (owner_id, precheck[0]))
            db.execute('DELETE FROM prechecks WHERE photo_id=? AND owner_id=?', (photo_id, owner_id))
            db.execute('DELETE FROM photos WHERE id=? AND owner_id=?', (photo_id, owner_id))
            orphaned.append(photo_id)
        db.execute('''UPDATE revisions SET input_version=input_version+1,draft_version=draft_version+1,
            selected_run_id=NULL,wizard_step='sample',updated_at=? WHERE id=?''', (utc_now(), draft_id))
    for photo_id in orphaned:
        delete_photo_assets(owner_id, photo_id)
    return {'deleted_count': len(photo_ids)}


def _encode_png(image):
    ok, encoded = cv2.imencode('.png', image)
    if not ok:
        raise ValueError('Could not encode lossless image')
    return encoded.tobytes()


def _run_precheck(precheck_id):
    with transaction() as db:
        row = db.execute('''SELECT pc.id,pc.owner_id,pc.photo_id,p.original_key,p.sha256,
                            p.source_width,p.source_height,p.exif_orientation
                            FROM prechecks pc JOIN photos p ON p.id=pc.photo_id
                            WHERE pc.id=? AND pc.status IN ('queued','failed')''', (precheck_id,)).fetchone()
        if not row:
            return
        db.execute("UPDATE prechecks SET status='processing',error_text=NULL WHERE id=?", (precheck_id,))
        db.execute("UPDATE processing_jobs SET state='running' WHERE kind='precheck' AND target_id=? AND state='queued'",
                   (precheck_id,))
    owner_id, photo_id = row['owner_id'], row['photo_id']
    try:
        raw = read_asset(row['original_key'], row['sha256'])
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Stored photo could not be decoded')
        result = segment.detect_beans(image, target_w=config.TARGET_WIDTH, pad=config.CROP_PAD, details=True)
        canonical_key = photo_key(owner_id, photo_id, 'canonical.png')
        asset_hashes = {}
        asset_hashes[canonical_key] = write_asset(canonical_key, _encode_png(result.canonical))
        annotation_key = photo_key(owner_id, photo_id, 'precheck.jpg')
        asset_hashes[annotation_key] = write_asset(annotation_key, render_precheck(result))
        objects = result.objects
        by_id = {obj['id']: obj for obj in objects}
        for bean in result.beans:
            object_id = bean['object_id']
            obj = by_id[object_id]
            obj['crop_key'] = photo_key(owner_id, photo_id, f'{object_id}-crop.png')
            obj['mask_key'] = photo_key(owner_id, photo_id, f'{object_id}-mask.png')
            obj['prepared_key'] = photo_key(owner_id, photo_id, f'{object_id}-prepared.png')
            asset_hashes[obj['crop_key']] = write_asset(obj['crop_key'], _encode_png(bean['crop']))
            asset_hashes[obj['mask_key']] = write_asset(obj['mask_key'], _encode_png(bean['mask']))
            asset_hashes[obj['prepared_key']] = write_asset(obj['prepared_key'],
                _encode_png(classify.prepare_crop(bean['crop'], mask=bean['mask'])))
            obj['prepared_sha256'] = asset_hashes[obj['prepared_key']]
        for key, checksum in asset_hashes.items():
            if cv2.imdecode(np.frombuffer(read_asset(key, checksum), np.uint8), cv2.IMREAD_UNCHANGED) is None:
                raise ValueError(f'Stored image is unreadable: {key}')
        excluded_percent = 100 * result.excluded_count / result.detected_count if result.detected_count else None
        excluded_severity = ('none' if excluded_percent is None or excluded_percent <= 5 else
                             'review' if excluded_percent <= 25 else
                             'high' if excluded_percent <= 50 else 'critical')
        warnings = []
        if not result.roi_detected:
            warnings.append('The paper background could not be identified reliably. Review the boxes on the photo.')
        if result.suspicious:
            warnings.append('Many fragments or excluded areas were detected. Retake this photo.')
        if excluded_percent is not None and excluded_percent > 5:
            warnings.append(f'{excluded_percent:.1f}% of detected candidates were excluded.')
        if 0 < result.usable_count < 5:
            warnings.append('This photo adds only 1–4 usable beans.')
        # Excluded candidates never block the valid beans in the same photo. A photo is
        # invalid only when precheck cannot produce any classifier input at all.
        status = ('invalid' if result.usable_count == 0 else
                  'warning' if warnings else 'ready')
        manifest = {
            'schema_version': 1, 'segmentation_version': 'mvp-1+diagnostics-1',
            'preprocessing_version': 'mvp-1',
            'photo_id': photo_id, 'source_width': result.source_width,
            'source_height': result.source_height,
            'original_width': row['source_width'], 'original_height': row['source_height'],
            'exif_orientation': row['exif_orientation'],
            'canonical_width': result.canonical.shape[1],
            'canonical_height': result.canonical.shape[0],
            'roi_detected': result.roi_detected,
            'initial_component_count': result.initial_component_count,
            'ignored_noise_count': result.ignored_noise_count,
            'fragment_area_ratio': result.fragment_area_ratio,
            'usable_count': result.usable_count,
            'excluded_count': result.excluded_count,
            'detected_count': result.detected_count,
            'excluded_reasons': result.reasons,
            'excluded_percent': excluded_percent,
            'excluded_severity': excluded_severity,
            'warnings': warnings, 'objects': objects,
            'canonical_key': canonical_key,
            'annotation_key': annotation_key,
            'asset_hashes': asset_hashes,
        }
        payload = json.dumps(manifest, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        manifest_key = photo_key(owner_id, photo_id, 'precheck.json')
        manifest_sha = write_asset(manifest_key, payload)
        removed_while_running = False
        with transaction() as db:
            current = db.execute('SELECT status FROM prechecks WHERE id=? AND owner_id=?',
                                 (precheck_id, owner_id)).fetchone()
            if not current:
                removed_while_running = True
            elif current['status'] != 'processing':
                return
            else:
                db.execute('UPDATE photos SET canonical_key=?,width=?,height=? WHERE id=? AND owner_id=?',
                           (canonical_key, result.canonical.shape[1], result.canonical.shape[0], photo_id, owner_id))
                db.execute('''UPDATE prechecks SET status=?,manifest_key=?,manifest_sha256=?,annotation_key=?,
                              usable_count=?,excluded_count=?,completed_at=? WHERE id=? AND owner_id=?''',
                           (status, manifest_key, manifest_sha, annotation_key,
                            result.usable_count, result.excluded_count, utc_now(), precheck_id, owner_id))
                db.execute("UPDATE processing_jobs SET state='succeeded',completed_at=? WHERE kind='precheck' AND target_id=? AND state='running'",
                           (utc_now(), precheck_id))
                review_state = 'included' if result.usable_count else 'omitted'
                membership = db.execute('''SELECT revision_id,review_state FROM revision_photos
                    WHERE precheck_id=? AND photo_id=?''', (precheck_id, photo_id)).fetchone()
                if membership and membership['review_state'] != review_state:
                    db.execute('UPDATE revision_photos SET review_state=? WHERE revision_id=? AND photo_id=?',
                               (review_state, membership['revision_id'], photo_id))
                    db.execute('''UPDATE revisions SET input_version=input_version+1,
                        draft_version=draft_version+1,selected_run_id=NULL,updated_at=? WHERE id=? AND state='draft' ''',
                               (utc_now(), membership['revision_id']))
        if removed_while_running:
            delete_photo_assets(owner_id, photo_id)
            return
        log.info('precheck %s: %d usable, %d excluded, status %s', photo_id,
                 result.usable_count, result.excluded_count, status)
    except Exception as exc:
        log.exception('precheck failed for %s', photo_id)
        with transaction() as db:
            db.execute("UPDATE prechecks SET status='failed',error_text=?,completed_at=? WHERE id=? AND status='processing'",
                       (str(exc)[:500], utc_now(), precheck_id))
            db.execute("UPDATE processing_jobs SET state='failed',error_text=?,completed_at=? WHERE kind='precheck' AND target_id=? AND state='running'",
                       (str(exc)[:500], utc_now(), precheck_id))
            retained_photo = db.execute('SELECT 1 FROM photos WHERE id=? AND owner_id=?',
                                        (photo_id, owner_id)).fetchone()
        if not retained_photo:
            delete_photo_assets(owner_id, photo_id)


def _photo_row(db, owner_id, draft_id, photo_id):
    return db.execute('''SELECT p.id,p.filename,p.width,p.height,p.media_type,p.created_at,
        rp.review_state,rp.sort_order,pc.id AS precheck_id,pc.status,pc.usable_count,
        pc.excluded_count,pc.error_text,pc.manifest_key,pc.manifest_sha256
        FROM revisions r JOIN revision_photos rp ON rp.revision_id=r.id
        JOIN photos p ON p.id=rp.photo_id JOIN prechecks pc ON pc.id=rp.precheck_id
        WHERE r.id=? AND r.owner_id=? AND r.state='draft' AND p.id=?''',
        (draft_id, owner_id, photo_id)).fetchone()


def _photo_dict(row, draft_id):
    item = {key: row[key] for key in ('id','filename','width','height','media_type','created_at',
                                       'review_state','sort_order','precheck_id','status',
                                       'usable_count','excluded_count','error_text')}
    if row['manifest_key']:
        manifest = json.loads(read_asset(row['manifest_key'], row['manifest_sha256']))
        item.update({key: manifest[key] for key in ('detected_count','excluded_reasons',
                                                   'excluded_percent','excluded_severity',
                                                   'warnings','roi_detected')})
        item['warnings'] = precheck_warnings(manifest)
    item['image_url'] = (f"/api/drafts/{draft_id}/photos/{row['id']}/image/"
                         f"{'precheck' if row['manifest_key'] else 'original'}")
    return item


def get_photo(owner_id, draft_id, photo_id):
    with read_connection() as db:
        row = _photo_row(db, owner_id, draft_id, photo_id)
    if not row:
        raise DomainError('Photo not found.', 404)
    return _photo_dict(row, draft_id)


def list_photos(owner_id, draft_id):
    with read_connection() as db:
        exists = db.execute("SELECT 1 FROM revisions WHERE id=? AND owner_id=? AND state='draft'",
                            (draft_id, owner_id)).fetchone()
        if not exists:
            raise DomainError('Draft not found.', 404)
        rows = db.execute('''SELECT p.id FROM revision_photos rp JOIN photos p ON p.id=rp.photo_id
            WHERE rp.revision_id=? ORDER BY rp.sort_order,p.id''', (draft_id,)).fetchall()
    return [get_photo(owner_id, draft_id, row['id']) for row in rows]


def photo_summary(items):
    included = [item for item in items if item['review_state'] == 'included']
    usable = sum(item['usable_count'] or 0 for item in included)
    excluded = sum(item['excluded_count'] or 0 for item in included)
    return {
        'photo_count': len(items), 'included_photo_count': len(included),
        'pending_review_count': sum(item['review_state'] == 'pending' for item in items),
        'processing_count': sum(item['status'] in ('queued', 'processing') for item in items),
        'usable_count': usable, 'excluded_count': excluded,
        'detected_count': usable + excluded,
        'sample_band': sample_band(usable) if included else
                       {'id': 'none', 'label': 'No sample yet', 'description': 'Select photos to use.'},
    }


def photo_image(owner_id, draft_id, photo_id, kind):
    if kind not in ('original', 'precheck'):
        raise DomainError('Unknown image type.', 404)
    with read_connection() as db:
        row = db.execute('''SELECT p.original_key,p.sha256,p.media_type,
            pc.annotation_key,pc.manifest_key,pc.manifest_sha256 FROM revisions r JOIN revision_photos rp ON rp.revision_id=r.id
            JOIN photos p ON p.id=rp.photo_id JOIN prechecks pc ON pc.id=rp.precheck_id
            WHERE r.id=? AND r.owner_id=? AND p.id=?''', (draft_id, owner_id, photo_id)).fetchone()
    if not row:
        raise DomainError('Photo not found.', 404)
    if kind == 'original':
        return read_asset(row['original_key'], row['sha256']), row['media_type']
    if not row['annotation_key']:
        raise DomainError('Photo precheck is not available yet.', 409)
    manifest = json.loads(read_asset(row['manifest_key'], row['manifest_sha256']))
    return read_asset(row['annotation_key'], manifest['asset_hashes'][row['annotation_key']]), 'image/jpeg'


def review_photo(owner_id, draft_id, photo_id, expected_input_version, choice):
    if choice not in ('included', 'omitted'):
        raise DomainError('Unknown photo selection.')
    with transaction() as db:
        revision = db.execute("SELECT input_version FROM revisions WHERE id=? AND owner_id=? AND state='draft'",
                              (draft_id, owner_id)).fetchone()
        row = _photo_row(db, owner_id, draft_id, photo_id)
        if not revision or not row:
            raise DomainError('Photo or draft not found.', 404)
        if revision['input_version'] != expected_input_version:
            raise DomainError('The sample was changed in another tab. Refresh to see the latest version.', 409)
        if choice == 'included' and row['status'] not in ('ready', 'warning'):
            raise DomainError('This photo is not ready to use.', 409)
        if row['review_state'] != choice:
            db.execute('UPDATE revision_photos SET review_state=? WHERE revision_id=? AND photo_id=?',
                       (choice, draft_id, photo_id))
            db.execute('''UPDATE revisions SET input_version=input_version+1,draft_version=draft_version+1,
                selected_run_id=NULL,updated_at=? WHERE id=?''', (utc_now(), draft_id))
    return get_photo(owner_id, draft_id, photo_id)


def use_all_ready(owner_id, draft_id, expected_input_version):
    """Normalize older drafts to the automatic include-valid-photo policy."""
    with transaction() as db:
        revision = db.execute("SELECT input_version FROM revisions WHERE id=? AND owner_id=? AND state='draft'",
                              (draft_id, owner_id)).fetchone()
        if not revision:
            raise DomainError('Draft not found.', 404)
        if revision['input_version'] != expected_input_version:
            raise DomainError('The sample was changed in another tab. Refresh to see the latest version.', 409)
        photo_ids = [row['photo_id'] for row in db.execute('''SELECT rp.photo_id FROM revision_photos rp
            JOIN prechecks pc ON pc.id=rp.precheck_id WHERE rp.revision_id=?
            AND rp.review_state='pending' AND pc.status IN ('ready','warning') ''', (draft_id,))]
        omitted_ids = [row['photo_id'] for row in db.execute('''SELECT rp.photo_id FROM revision_photos rp
            JOIN prechecks pc ON pc.id=rp.precheck_id WHERE rp.revision_id=?
            AND rp.review_state='pending' AND pc.status='invalid' ''', (draft_id,))]
        if photo_ids:
            db.executemany("UPDATE revision_photos SET review_state='included' WHERE revision_id=? AND photo_id=?",
                           [(draft_id, photo_id) for photo_id in photo_ids])
        if omitted_ids:
            db.executemany("UPDATE revision_photos SET review_state='omitted' WHERE revision_id=? AND photo_id=?",
                           [(draft_id, photo_id) for photo_id in omitted_ids])
        if photo_ids or omitted_ids:
            db.execute('''UPDATE revisions SET input_version=input_version+1,draft_version=draft_version+1,
                selected_run_id=NULL,updated_at=? WHERE id=?''', (utc_now(), draft_id))
    return {'included_count': len(photo_ids), 'omitted_count': len(omitted_ids)}


def retry_precheck(owner_id, draft_id, photo_id):
    with transaction() as db:
        row = _photo_row(db, owner_id, draft_id, photo_id)
        if not row:
            raise DomainError('Photo not found.', 404)
        if row['status'] != 'failed':
            raise DomainError('Only photos with failed prechecks can be retried.', 409)
        if db.execute('SELECT 1 FROM revision_photos WHERE photo_id=? AND revision_id<>? LIMIT 1',
                      (photo_id, draft_id)).fetchone():
            raise DomainError('This photo belongs to a finalized revision. Replace it in the draft to retry.', 409)
        db.execute("UPDATE prechecks SET status='queued',error_text=NULL WHERE id=?", (row['precheck_id'],))
        db.execute('''INSERT INTO processing_jobs(id,owner_id,kind,target_id,state,created_at)
                      VALUES (?,?,?,?,?,?)''', (_id(), owner_id, 'precheck', row['precheck_id'], 'queued', utc_now()))
    _schedule(row['precheck_id'])
    return get_photo(owner_id, draft_id, photo_id)


def _included_input(owner_id, draft_id):
    with read_connection() as db:
        require_draft_supplier(db, owner_id, draft_id)
        rows = db.execute('''SELECT p.id AS photo_id,pc.id AS precheck_id,pc.status,
            pc.usable_count,pc.excluded_count,pc.manifest_key,pc.manifest_sha256,
            rp.review_state,rp.sort_order
            FROM revisions r JOIN revision_photos rp ON rp.revision_id=r.id
            JOIN photos p ON p.id=rp.photo_id JOIN prechecks pc ON pc.id=rp.precheck_id
            WHERE r.id=? AND r.owner_id=? AND r.state='draft'
            ORDER BY rp.sort_order,p.id''', (draft_id, owner_id)).fetchall()
    if not rows:
        raise DomainError('Draft not found or has no photos yet.', 404)
    if any(row['review_state'] == 'pending' for row in rows):
        raise DomainError('Review or skip each photo before running the analysis.', 409)
    included = []
    for row in rows:
        if row['review_state'] != 'included':
            continue
        if row['status'] not in ('ready', 'warning') or not row['manifest_key']:
            raise DomainError('Every selected photo must have a completed precheck.', 409)
        manifest_raw = read_asset(row['manifest_key'], row['manifest_sha256'])
        manifest = json.loads(manifest_raw)
        accepted = [obj for obj in manifest['objects'] if obj['disposition'] == 'usable']
        if len(accepted) != row['usable_count']:
            raise DomainError('Precheck bean counts do not match the saved data.', 409)
        included.append({
            'photo_id': row['photo_id'], 'precheck_id': row['precheck_id'],
            'sort_order': row['sort_order'], 'manifest_key': row['manifest_key'],
            'manifest_sha256': row['manifest_sha256'], 'usable_count': row['usable_count'],
            'excluded_count': row['excluded_count'],
            'bean_ids': [obj['id'] for obj in accepted],
        })
    if not included or sum(item['usable_count'] for item in included) == 0:
        raise DomainError('Select at least one photo with usable beans.', 409)
    return included


def start_analysis(owner_id, draft_id, expected_input_version, confirm_small_sample=False):
    included = _included_input(owner_id, draft_id)
    usable_total = sum(item['usable_count'] for item in included)
    if usable_total < 50 and not confirm_small_sample:
        raise DomainError('The sample contains fewer than 50 beans. Confirm to view indicative results.', 409)
    snapshot = {'schema_version': 1, 'draft_id': draft_id,
                'input_version': expected_input_version, 'photos': included,
                'usable_count': usable_total,
                'excluded_count': sum(item['excluded_count'] for item in included)}
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    input_sha = hashlib.sha256(payload).hexdigest()
    run_id, job_id, now = _id(), _id(), utc_now()
    input_key = photo_key(owner_id, run_id, 'inputs.json')
    write_asset(input_key, payload)
    try:
        with transaction() as db:
            revision = db.execute('''SELECT r.input_version,r.selected_run_id FROM revisions r
                WHERE r.id=? AND r.owner_id=? AND r.state='draft' ''', (draft_id, owner_id)).fetchone()
            if not revision:
                raise DomainError('Draft not found.', 404)
            if revision['input_version'] != expected_input_version:
                raise DomainError('The sample was changed in another tab. Refresh before running the analysis.', 409)
            active = db.execute("SELECT id,status,input_sha256 FROM analysis_runs WHERE id=? AND owner_id=?",
                                (revision['selected_run_id'], owner_id)).fetchone() if revision['selected_run_id'] else None
            if active and active['input_sha256'] == input_sha and active['status'] in ('queued', 'processing', 'complete'):
                delete_photo_assets(owner_id, run_id)
                return {'id': active['id'], 'status': active['status']}
            db.execute('''INSERT INTO analysis_runs(id,owner_id,revision_id,input_version,input_sha256,status,
                usable_count,excluded_count,photo_count,created_at)
                VALUES (?,?,?,?,?,'queued',?,?,?,?)''',
                (run_id, owner_id, draft_id, expected_input_version, input_sha,
                 usable_total, snapshot['excluded_count'], len(included), now))
            db.execute('''INSERT INTO processing_jobs(id,owner_id,kind,target_id,state,created_at)
                          VALUES (?,?,?,?,?,?)''', (job_id, owner_id, 'classify', run_id, 'queued', now))
            db.execute('''UPDATE revisions SET selected_run_id=?,wizard_step='result',
                draft_version=draft_version+1,updated_at=? WHERE id=?''', (run_id, now, draft_id))
    except Exception:
        delete_photo_assets(owner_id, run_id)
        raise
    if _classifier is None:
        with transaction() as db:
            db.execute("UPDATE analysis_runs SET status='failed',error_text='The analysis model is unavailable.' WHERE id=?", (run_id,))
            db.execute("UPDATE processing_jobs SET state='failed',error_text='The analysis model is unavailable.',completed_at=? WHERE id=?",
                       (utc_now(), job_id))
        raise DomainError('The analysis model is unavailable on this server.', 503)
    _executor.submit(_run_classification, run_id)
    return {'id': run_id, 'status': 'queued'}


def _annotate_result(canonical, manifest, labels):
    from core.precheck import COLORS
    canvas = canonical.copy()
    class_colors = {'fermented': (30, 185, 35), 'poorly_fermented': (40, 40, 225)}
    index = 0
    for obj in manifest['objects']:
        x, y, w, h = obj['bbox']
        if obj['disposition'] == 'usable':
            label = labels[index]
            index += 1
            color = class_colors[label]
            text = f"{index} {grade.LABEL_ID[label]}"
        else:
            color = COLORS[obj['reason']]
            text = obj['reason'].replace('_', ' ')
        cv2.rectangle(canvas, (x, y), (x + w, y + h), color, 3 if obj['disposition'] == 'usable' else 2)
        cv2.putText(canvas, text, (x, max(22, y - 7)), cv2.FONT_HERSHEY_SIMPLEX, .5,
                    color, 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError('Could not encode final annotation')
    return encoded.tobytes()


def _run_classification(run_id):
    with transaction() as db:
        run = db.execute('''SELECT a.*,r.input_version AS current_input_version,
            r.selected_run_id,r.owner_id AS revision_owner FROM analysis_runs a
            JOIN revisions r ON r.id=a.revision_id WHERE a.id=? AND a.status='queued' ''', (run_id,)).fetchone()
        if not run:
            return
        if _classifier is None:
            db.execute("UPDATE analysis_runs SET status='failed',error_text='The analysis model is unavailable.' WHERE id=?", (run_id,))
            db.execute("UPDATE processing_jobs SET state='failed',error_text='The analysis model is unavailable.',completed_at=? WHERE target_id=? AND kind='classify'",
                       (utc_now(), run_id))
            return
        db.execute("UPDATE analysis_runs SET status='processing' WHERE id=?", (run_id,))
        db.execute("UPDATE processing_jobs SET state='running' WHERE kind='classify' AND target_id=? AND state='queued'",
                   (run_id,))
    owner_id = run['owner_id']
    try:
        input_key = photo_key(owner_id, run_id, 'inputs.json')
        input_payload = read_asset(input_key, run['input_sha256'])
        snapshot = json.loads(input_payload)
        if snapshot['input_version'] != run['input_version']:
            raise ValueError('Analysis input version differs from its snapshot')
        all_crops, photo_inputs = [], []
        for photo in snapshot['photos']:
            precheck_payload = read_asset(photo['manifest_key'], photo['manifest_sha256'])
            precheck = json.loads(precheck_payload)
            accepted = [obj for obj in precheck['objects'] if obj['disposition'] == 'usable']
            accepted_ids = [obj['id'] for obj in accepted]
            if accepted_ids != photo['bean_ids'] or len(accepted_ids) != photo['usable_count']:
                raise ValueError('Saved precheck bean set differs from the analysis snapshot')
            start = len(all_crops)
            for obj in accepted:
                prepared_key = obj['prepared_key']
                expected_hash = precheck['asset_hashes'][prepared_key]
                prepared = cv2.imdecode(np.frombuffer(read_asset(prepared_key, expected_hash), np.uint8),
                                        cv2.IMREAD_COLOR)
                if prepared is None:
                    raise ValueError(f"Prepared bean input is missing or invalid: {obj['id']}")
                all_crops.append(prepared)
            photo_inputs.append((photo, precheck, accepted, start, len(all_crops)))
        labels_data = classify.classify_beans(_classifier, all_crops)
        if len(labels_data) != snapshot['usable_count']:
            raise ValueError('Classifier output count differs from the accepted precheck bean set')
        labels = [item['label'] for item in labels_data]
        if any(label not in config.CLASS_NAMES for label in labels):
            raise ValueError('Classifier returned an unknown fermentation label')
        if sum(label == 'fermented' for label in labels) + sum(label == 'poorly_fermented' for label in labels) != len(all_crops):
            raise ValueError('Fermentation counts do not reconcile with analyzed beans')
        per_photo, result_hashes = [], {}
        for photo, precheck, accepted, start, end in photo_inputs:
            photo_labels = labels[start:end]
            if len(photo_labels) != len(accepted):
                raise ValueError('Per-photo prediction count differs from its saved accepted set')
            canonical_key = precheck['canonical_key']
            canonical = cv2.imdecode(np.frombuffer(
                read_asset(canonical_key, precheck['asset_hashes'][canonical_key]), np.uint8), cv2.IMREAD_COLOR)
            if canonical is None:
                raise ValueError('Canonical photo is missing or invalid')
            annotation = _annotate_result(canonical, precheck, photo_labels)
            annotation_key = photo_key(owner_id, run_id, f"photo-{photo['photo_id']}.jpg")
            result_hashes[annotation_key] = write_asset(annotation_key, annotation)
            per_photo.append({
                'photo_id': photo['photo_id'], 'precheck_id': photo['precheck_id'],
                'usable_count': len(photo_labels), 'excluded_count': photo['excluded_count'],
                'fermented_count': photo_labels.count('fermented'),
                'poorly_count': photo_labels.count('poorly_fermented'),
                'annotation_key': annotation_key,
            })
        counts = grade.count_labels(labels)
        summary = grade.grade(labels, n_unreadable=0, n_photos=len(photo_inputs))
        summary['excluded_count'] = snapshot['excluded_count']
        summary['percent_exact'] = 100 * counts['fermented'] / len(labels)
        summary['sample_band'] = sample_band(len(labels))
        summary['detected_count'] = len(labels) + snapshot['excluded_count']
        summary['report'] = grade.format_report(grade.grade(labels, n_unreadable=0,
                                                            n_photos=len(photo_inputs)))
        result_manifest = {
            'schema_version': 1, 'run_id': run_id, 'revision_id': run['revision_id'],
            'input_version': run['input_version'], 'input_sha256': run['input_sha256'],
            'usable_count': len(labels), 'excluded_count': snapshot['excluded_count'],
            'detected_count': summary['detected_count'], 'counts': counts,
            'percent_exact': summary['percent_exact'], 'percent_rounded': summary['persen'],
            'sample_band': summary['sample_band'], 'notes': summary['catatan'],
            'disclaimer': summary['disclaimer'], 'report': summary['report'],
            'photos': per_photo, 'asset_hashes': result_hashes,
        }
        payload = json.dumps(result_manifest, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        result_key = photo_key(owner_id, run_id, 'result.json')
        result_sha = write_asset(result_key, payload)
        for key, checksum in result_hashes.items():
            if not read_asset(key, checksum):
                raise ValueError('Final annotation is empty')
        with transaction() as db:
            current = db.execute('''SELECT input_version,selected_run_id FROM revisions
                WHERE id=? AND owner_id=? AND state='draft' ''', (run['revision_id'], owner_id)).fetchone()
            if (not current or current['input_version'] != run['input_version']
                    or current['selected_run_id'] != run_id):
                raise ValueError('Draft sample changed while classification was running')
            db.execute('''UPDATE analysis_runs SET status='complete',manifest_key=?,manifest_sha256=?,
                fermented_count=?,poorly_count=?,completed_at=? WHERE id=? AND status='processing' ''',
                (result_key, result_sha, counts['fermented'], counts['poorly_fermented'], utc_now(), run_id))
            db.execute("UPDATE revisions SET wizard_step='result',draft_version=draft_version+1,updated_at=? WHERE id=?",
                       (utc_now(), run['revision_id']))
            db.execute("UPDATE processing_jobs SET state='succeeded',completed_at=? WHERE kind='classify' AND target_id=? AND state='running'",
                       (utc_now(), run_id))
        log.info('classification %s: %d analyzed, %d fermented, %d poorly fermented',
                 run_id, len(labels), counts['fermented'], counts['poorly_fermented'])
    except Exception as exc:
        log.exception('classification failed for %s', run_id)
        with transaction() as db:
            db.execute("UPDATE analysis_runs SET status='failed',error_text=?,completed_at=? WHERE id=? AND status='processing'",
                       (str(exc)[:500], utc_now(), run_id))
            db.execute("UPDATE processing_jobs SET state='failed',error_text=?,completed_at=? WHERE kind='classify' AND target_id=? AND state='running'",
                       (str(exc)[:500], utc_now(), run_id))
        delete_photo_assets(owner_id, run_id)


def _load_run(owner_id, run_id):
    with read_connection() as db:
        row = db.execute('''SELECT a.*,r.id AS revision_id FROM analysis_runs a
            JOIN revisions r ON r.id=a.revision_id JOIN lots l ON l.id=r.lot_id
            WHERE a.id=? AND a.owner_id=? AND r.owner_id=? AND l.owner_id=?''',
            (run_id, owner_id, owner_id, owner_id)).fetchone()
    if not row:
        raise DomainError('Analysis results not found.', 404)
    result = {key: row[key] for key in ('id','revision_id','status','input_version','usable_count',
                                        'excluded_count','photo_count','error_text','created_at','completed_at')}
    if row['status'] == 'complete' and row['manifest_key']:
        try:
            result['result'] = result_copy(json.loads(read_asset(row['manifest_key'], row['manifest_sha256'])))
        except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
            raise DomainError('Unable to read result evidence. Your draft remains saved.', 409) from exc
    return result


def result_for_draft(owner_id, draft_id):
    with read_connection() as db:
        row = db.execute("SELECT selected_run_id FROM revisions WHERE id=? AND owner_id=? AND state='draft'",
                         (draft_id, owner_id)).fetchone()
    if not row:
        raise DomainError('Draft not found.', 404)
    if not row['selected_run_id']:
        return {'status': 'idle'}
    return _load_run(owner_id, row['selected_run_id'])


def result_for_lot(owner_id, lot_id):
    from domain import get_finalized_lot
    lot = get_finalized_lot(owner_id, lot_id)
    return {'lot': lot, 'analysis': _load_run(owner_id, lot['selected_run_id'])}


def result_for_revision(owner_id, lot_id, revision_id):
    from domain import get_finalized_revision
    revision = get_finalized_revision(owner_id, lot_id, revision_id)
    return {'lot': revision, 'analysis': _load_run(owner_id, revision['selected_run_id'])}


def result_image(owner_id, run_id, photo_id):
    run = _load_run(owner_id, run_id)
    if run['status'] != 'complete':
        raise DomainError('Result image is not available yet.', 409)
    manifest = run['result']
    photo = next((item for item in manifest['photos'] if item['photo_id'] == photo_id), None)
    if not photo:
        raise DomainError('Result photo not found.', 404)
    return read_asset(photo['annotation_key'], manifest['asset_hashes'][photo['annotation_key']]), 'image/jpeg'


def verify_finalizable(owner_id, draft_id, expected_version):
    result = result_for_draft(owner_id, draft_id)
    if result['status'] != 'complete':
        raise DomainError('Wait for the analysis to finish before saving.', 409)
    with read_connection() as db:
        row = db.execute("SELECT draft_version,input_version FROM revisions WHERE id=? AND owner_id=? AND state='draft'",
                         (draft_id, owner_id)).fetchone()
    if not row:
        raise DomainError('Draft not found.', 404)
    if row['draft_version'] != expected_version:
        raise DomainError('The draft was changed in another tab. Refresh before saving.', 409)
    if result['input_version'] != row['input_version'] or result['usable_count'] <= 0:
        raise DomainError('Results no longer match the draft sample.', 409)
    return result
