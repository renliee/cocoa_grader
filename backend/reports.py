"""Immutable revision reports, public token access, PDF jobs, and LAN-aware QR."""
import hashlib
import io
import json
import os
import secrets
import socket
import ipaddress
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from db import read_connection, transaction
from domain import DomainError, get_finalized_revision
from security import utc_now
from presentation import result_copy
from storage import delete_photo_assets, photo_key, read_asset, write_asset

_executor = None
_TEMPLATE_VERSION = 3
_REPORT_LOGO = Path(__file__).resolve().parent / 'assets' / 'report-logo.png'
_REASONS = {
    'edge_cut': 'Cut off at edge',
    'unresolved_cluster': 'Unresolved cluster',
    'fragment': 'Fragment',
    'suspicious_geometry': 'Irregular geometry',
}


def _validate_origin(value):
    value = value.rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment or parsed.path or
            value != f'{parsed.scheme}://{parsed.netloc}'):
        raise DomainError('KAKAO_PUBLIC_BASE_URL must be an HTTP(S) origin without a path or credentials.', 503)
    try:
        _ = parsed.port
    except ValueError as exc:
        raise DomainError('Invalid report URL port.', 503) from exc
    return value


def _is_loopback(url):
    host = urlsplit(url).hostname
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def _lan_address():
    # A connected UDP socket asks the OS which interface serves the LAN; no packet is sent.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(('192.0.2.1', 80))
            address = connection.getsockname()[0]
        ip = ipaddress.ip_address(address)
        if ip.is_private and not ip.is_loopback and not ip.is_link_local and not ip.is_unspecified:
            return address
    except OSError:
        pass
    return None


def _base_url(request_origin=None):
    configured = os.environ.get('KAKAO_PUBLIC_BASE_URL', '').strip()
    if configured:
        return _validate_origin(configured)
    origin = _validate_origin(request_origin) if request_origin else 'http://127.0.0.1:8081'
    if not _is_loopback(origin):
        return origin
    # Container interface addresses are not reachable through the host's published port.
    if os.path.exists('/.dockerenv'):
        return origin
    lan = _lan_address()
    if not lan:
        return origin
    parsed = urlsplit(origin)
    return f'{parsed.scheme}://{lan}{":" + str(parsed.port) if parsed.port else ""}'


def _report_row(db, token):
    return db.execute('''SELECT r.*,e.status AS pdf_status,e.error_text AS pdf_error,
        e.pdf_key,e.pdf_sha256,e.template_version FROM reports r JOIN report_exports e ON e.report_id=r.id
        WHERE r.share_token=? AND r.revoked_at IS NULL''', (token,)).fetchone()


def _snapshot(row):
    try:
        return json.loads(read_asset(row['snapshot_key'], row['snapshot_sha256']))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise DomainError('Unable to read report data. Contact the lot owner.', 409) from exc


def _public_data(row, request_origin=None):
    payload = result_copy(_snapshot(row))
    visible = {key: value for key, value in payload.items() if key != 'asset_hashes'}
    visible['photos'] = [{key: value for key, value in photo.items()
                          if key not in ('annotation_key', 'annotation_sha256')}
                         | {'image_url': f"/api/reports/{row['share_token']}/photos/{photo['photo_id']}"}
                         for photo in payload['photos']]
    base = _base_url(request_origin)
    return {'report': visible, 'url': f"{base}/report/{row['share_token']}",
            'pdf_status': row['pdf_status'], 'pdf_error': row['pdf_error'],
            'lan_ready': not _is_loopback(base)}


def create_report(owner_id, lot_id, revision_id, request_origin=None):
    revision = get_finalized_revision(owner_id, lot_id, revision_id)
    with read_connection() as db:
        existing = db.execute('''SELECT share_token FROM reports WHERE revision_id=? AND owner_id=?
            AND revoked_at IS NULL''', (revision_id, owner_id)).fetchone()
    if existing:
        return get_report(existing['share_token'], request_origin)
    with read_connection() as db:
        run = db.execute('''SELECT manifest_key,manifest_sha256,status FROM analysis_runs
            WHERE id=? AND revision_id=? AND owner_id=?''',
            (revision['selected_run_id'], revision_id, owner_id)).fetchone()
    if not run or run['status'] != 'complete':
        raise DomainError('Finalized results are not ready for reporting.', 409)
    try:
        result = json.loads(read_asset(run['manifest_key'], run['manifest_sha256']))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise DomainError('Unable to read the finalized evidence.', 409) from exc
    reasons = {}
    photos = []
    for item in result['photos']:
        key = item['annotation_key']
        checksum = result['asset_hashes'][key]
        # Reject incomplete evidence before publishing any share token.
        try:
            if not read_asset(key, checksum):
                raise DomainError('Result image is unavailable.', 409)
        except (OSError, ValueError) as exc:
            raise DomainError('Unable to read the result image. The report has not been published.', 409) from exc
        photos.append({k: item[k] for k in ('photo_id','usable_count','excluded_count',
                                            'fermented_count','poorly_count')})
        photos[-1].update(annotation_key=key, annotation_sha256=checksum)
        with read_connection() as db:
            precheck = db.execute('''SELECT manifest_key,manifest_sha256 FROM prechecks
                WHERE id=? AND owner_id=?''', (item['precheck_id'],owner_id)).fetchone()
        if not precheck:
            raise DomainError('Precheck evidence for the finalized result is unavailable.',409)
        try:
            detail = json.loads(read_asset(precheck['manifest_key'],precheck['manifest_sha256']))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise DomainError('Unable to read precheck evidence. The report has not been published.',409) from exc
        for reason, count in detail.get('excluded_reasons', {}).items():
            reasons[reason] = reasons.get(reason, 0) + count
    payload = {
        'schema_version': 1, 'lot_id': lot_id, 'human_id': revision['human_id'],
        'supplier_name': revision['supplier_name'], 'weight_kg': revision['weight_kg'],
        'revision_id': revision_id, 'revision_number': revision['revision_number'],
        'analysis_date': revision['finalized_at'], 'usable_count': result['usable_count'],
        'excluded_count': result['excluded_count'], 'detected_count': result['detected_count'],
        'counts': result['counts'], 'percent_exact': result['percent_exact'],
        'percent_rounded': result['percent_rounded'], 'sample_band': result['sample_band'],
        'exclusion_reasons': reasons, 'notes': result.get('notes', []),
        'disclaimer': result['disclaimer'], 'photos': photos,
    }
    if sum(photo['usable_count'] for photo in photos) != payload['usable_count']:
        raise DomainError('Photo counts do not match the finalized result.',409)
    if sum(photo['excluded_count'] for photo in photos) != payload['excluded_count']:
        raise DomainError('Excluded object counts do not match.',409)
    if sum(reasons.values()) != payload['excluded_count']:
        raise DomainError('The excluded object breakdown does not match.',409)
    report_id = uuid4().hex
    token = secrets.token_urlsafe(32)
    key = photo_key(owner_id, report_id, 'snapshot.json')
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    checksum = write_asset(key, raw)
    created = False
    try:
        with transaction() as db:
            existing = db.execute('SELECT share_token FROM reports WHERE revision_id=? AND owner_id=?',
                                  (revision_id, owner_id)).fetchone()
            if not existing:
                db.execute('''INSERT INTO reports(id,owner_id,revision_id,share_token,snapshot_key,
                    snapshot_sha256,created_at) VALUES (?,?,?,?,?,?,?)''',
                    (report_id,owner_id,revision_id,token,key,checksum,utc_now()))
                db.execute('''INSERT INTO report_exports(report_id,status,template_version,payload_sha256,updated_at)
                    VALUES (?,'queued',?,?,?)''', (report_id,_TEMPLATE_VERSION,checksum,utc_now()))
                created = True
        if not created:
            delete_photo_assets(owner_id, report_id)
            return get_report(existing['share_token'], request_origin)
    except Exception:
        delete_photo_assets(owner_id, report_id)
        raise
    if _executor is not None:
        _executor.submit(_build_pdf, report_id)
    return get_report(token, request_origin)


def get_report(token, request_origin=None):
    with read_connection() as db:
        row = _report_row(db, token)
    if not row:
        raise DomainError('Report not found or no longer available.',404)
    if row['pdf_status'] == 'complete' and row['template_version'] < _TEMPLATE_VERSION:
        with transaction() as db:
            changed = db.execute('''UPDATE report_exports SET status='queued',template_version=?,updated_at=?
                WHERE report_id=? AND status='complete' AND template_version<?''',
                (_TEMPLATE_VERSION,utc_now(),row['id'],_TEMPLATE_VERSION)).rowcount
        if changed and _executor is not None:
            _executor.submit(_build_pdf,row['id'])
        if changed:
            with read_connection() as db:
                row = _report_row(db, token)
    return _public_data(row, request_origin)


def report_photo(token, photo_id):
    with read_connection() as db:
        row = _report_row(db, token)
    if not row:
        raise DomainError('Report not found.',404)
    photo = next((item for item in _snapshot(row)['photos'] if item['photo_id']==photo_id),None)
    if not photo:
        raise DomainError('Report photo not found.',404)
    try:
        return read_asset(photo['annotation_key'],photo['annotation_sha256'])
    except (OSError,ValueError) as exc:
        raise DomainError('Unable to read the report image evidence.',409) from exc


def report_pdf(token):
    get_report(token)
    with read_connection() as db:
        row = _report_row(db, token)
    if not row:
        raise DomainError('Report not found.',404)
    if row['pdf_status'] != 'complete':
        raise DomainError('The PDF is not ready. Check the report status and retry.',409)
    try:
        return read_asset(row['pdf_key'],row['pdf_sha256'])
    except (OSError,ValueError) as exc:
        raise DomainError('Unable to read the PDF. The owner can retry the export.',409) from exc


def report_qr(token, request_origin=None):
    data = get_report(token, request_origin)
    if not data['lan_ready']:
        raise DomainError('Open KakaoLens using this device’s LAN address, or configure KAKAO_PUBLIC_BASE_URL with an address reachable from your phone.',409)
    image = qrcode.make(data['url'],border=3)
    output = io.BytesIO()
    image.save(output,format='PNG')
    return output.getvalue()


def retry_pdf(owner_id, lot_id, revision_id):
    get_finalized_revision(owner_id,lot_id,revision_id)
    with transaction() as db:
        row = db.execute('''SELECT e.report_id,e.status FROM report_exports e JOIN reports r ON r.id=e.report_id
            WHERE r.revision_id=? AND r.owner_id=? AND r.revoked_at IS NULL''',
            (revision_id,owner_id)).fetchone()
        if not row:
            raise DomainError('Create the report first.',404)
        if row['status'] != 'running':
            db.execute('''UPDATE report_exports SET status='queued',template_version=?,error_text=NULL,updated_at=?
                WHERE report_id=?''',(_TEMPLATE_VERSION,utc_now(),row['report_id']))
    if _executor is not None and row['status'] != 'running':
        _executor.submit(_build_pdf,row['report_id'])
    return {'status': 'queued' if row['status'] != 'running' else 'running'}


def start_worker():
    global _executor
    _executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix='kakao-pdf')
    with transaction() as db:
        pending = [row['report_id'] for row in db.execute(
            "SELECT report_id FROM report_exports WHERE status IN ('queued','running')")]
        db.execute("UPDATE report_exports SET status='queued' WHERE status='running'")
    for report_id in pending:
        _executor.submit(_build_pdf,report_id)


def stop_worker():
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None


def _short(value, max_width, font='Helvetica', size=10):
    value = str(value or '—')
    if stringWidth(value,font,size) <= max_width:
        return value
    while value and stringWidth(value+'…',font,size)>max_width:
        value=value[:-1]
    return value+'…'


def _draw_pdf(payload):
    output=io.BytesIO()
    pdf=canvas.Canvas(output,pagesize=A4,pageCompression=1)
    width,height=A4
    margin=45
    dark='#224633'
    def line(label,value,y):
        pdf.setFont('Helvetica',10)
        pdf.setFillColor('#607061')
        pdf.drawString(margin,y,label)
        pdf.setFont('Helvetica-Bold',10)
        pdf.setFillColor(dark)
        pdf.drawRightString(width-margin,y,_short(value,270,'Helvetica-Bold',10))
    pdf.setFillColor(dark)
    pdf.rect(0,height-120,width,120,fill=1,stroke=0)
    logo = ImageReader(str(_REPORT_LOGO))
    pdf.setFillColor('#ffffff')
    pdf.roundRect(margin,height-98,205,76,8,fill=1,stroke=0)
    pdf.drawImage(logo,margin+8,height-93,width=189,height=66,preserveAspectRatio=True,anchor='c',mask='auto')
    pdf.setFont('Helvetica',11)
    pdf.drawString(margin+220,height-68,'Analysis report')
    pdf.drawString(margin+220,height-85,'Cocoa fermentation')
    pdf.setFillColor(dark)
    pdf.setFont('Helvetica-Bold',17)
    pdf.drawString(margin,height-151,_short(payload['human_id'],width-2*margin,'Helvetica-Bold',17))
    supplier_words = str(payload['supplier_name'] or '').split()
    supplier_lines = []
    current = ''
    for word in supplier_words:
        if stringWidth(word,'Helvetica-Bold',10) > 280:
            if current:
                supplier_lines.append(current)
                current = ''
            chunk = ''
            for char in word:
                if chunk and stringWidth(chunk+char,'Helvetica-Bold',10) > 280:
                    supplier_lines.append(chunk)
                    chunk = ''
                chunk += char
            current = chunk
            continue
        candidate = f'{current} {word}'.strip()
        if current and stringWidth(candidate,'Helvetica-Bold',10) > 280:
            supplier_lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        supplier_lines.append(current)
    pdf.setFont('Helvetica',10)
    pdf.setFillColor('#607061')
    pdf.drawString(margin,height-185,'Supplier')
    pdf.setFont('Helvetica-Bold',10)
    pdf.setFillColor(dark)
    for index, value in enumerate(supplier_lines or ['—']):
        pdf.drawRightString(width-margin,height-185-index*13,value)
    shift = max(0,len(supplier_lines)-1)*13
    finalized_at = datetime.fromisoformat(payload['analysis_date'].replace('Z','+00:00'))
    if finalized_at.tzinfo is None:
        finalized_at = finalized_at.replace(tzinfo=timezone.utc)
    line('Analysis date',finalized_at.astimezone(timezone.utc).strftime('%d %b %Y, %H:%M UTC'),height-207-shift)
    line('Revision',payload['revision_number'],height-229-shift)
    line('Lot weight',f"{payload['weight_kg']} kg" if payload['weight_kg'] else 'Not recorded',height-251-shift)
    pdf.setStrokeColor('#d7e4d7')
    pdf.line(margin,height-271-shift,width-margin,height-271-shift)
    line('Beans analyzed',payload['usable_count'],height-297-shift)
    line('Excluded objects',payload['excluded_count'],height-319-shift)
    line('Sample sufficiency',result_copy(payload)['sample_band']['label'],height-341-shift)
    line('Well fermented',f"{payload['counts']['fermented']} beans / {payload['percent_rounded']['fermented']}%",height-380-shift)
    line('Poorly fermented',f"{payload['counts']['poorly_fermented']} beans / {payload['percent_rounded']['poorly_fermented']}%",height-402-shift)
    y=height-435-shift
    pdf.setFont('Helvetica-Bold',10)
    pdf.drawString(margin,y,'Exclusion summary')
    y-=19
    pdf.setFont('Helvetica',9)
    if payload['exclusion_reasons']:
        for reason,count in payload['exclusion_reasons'].items():
            pdf.drawString(margin+12,y,f"{_REASONS.get(reason,reason)}: {count}")
            y-=16
    else:
        pdf.drawString(margin+12,y,'No objects excluded.')
        y-=16
    y-=13
    if payload['usable_count']<50:
        warning='Very limited sample (<50); excluded from summary statistics.'
    elif payload['usable_count']<300:
        warning='Below the 300-bean reference; results are indicative.'
    else:
        warning='The 300-bean reference is met; representativeness still matters.'
    pdf.setFillColor('#855333' if payload['usable_count']<300 else dark)
    pdf.setFont('Helvetica-Bold',9)
    pdf.drawString(margin,y,warning)
    y-=28
    pdf.setFillColor(dark)
    pdf.setFont('Helvetica',9)
    for note in ('KakaoLens assesses visual fermentation characteristics.',
                 'This report is not a comprehensive quality test or an official SNI assessment.'):
        pdf.drawString(margin,y,note)
        y-=15
    pdf.setFont('Helvetica',8)
    pdf.setFillColor('#6d796d')
    pdf.drawString(margin,40,'KakaoLens - Finalized revision evidence')
    pdf.drawRightString(width-margin,40,'1')
    pdf.showPage()
    for index,photo in enumerate(payload['photos'],1):
        image=read_asset(photo['annotation_key'],photo['annotation_sha256'])
        reader=ImageReader(io.BytesIO(image))
        image_w,image_h=reader.getSize()
        scale=min((width-2*margin)/image_w,(height-220)/image_h)
        fitted_w,fitted_h=image_w*scale,image_h*scale
        pdf.setFillColor(dark)
        pdf.setFont('Helvetica-Bold',14)
        pdf.drawString(margin,height-65,f"{payload['human_id']} - Revision {payload['revision_number']}")
        pdf.drawImage(logo,width-margin-145,height-95,width=145,height=48,
                      preserveAspectRatio=True,anchor='c',mask='auto')
        pdf.setFont('Helvetica',10)
        pdf.drawString(margin,height-89,f"Photo {index} of {len(payload['photos'])}")
        pdf.drawImage(reader,(width-fitted_w)/2,height-115-fitted_h,
                      width=fitted_w,height=fitted_h,preserveAspectRatio=True)
        y=height-135-fitted_h
        pdf.setFont('Helvetica',10)
        pdf.drawString(margin,y,f"Analyzed: {photo['usable_count']} beans   Well fermented: {photo['fermented_count']}")
        pdf.drawString(margin,y-17,f"Poorly fermented: {photo['poorly_count']}   Excluded: {photo['excluded_count']}")
        pdf.setFillColor('#6d796d')
        pdf.setFont('Helvetica',8)
        pdf.drawString(margin,40,'KakaoLens - Annotated image evidence')
        pdf.drawRightString(width-margin,40,str(index+1))
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def _build_pdf(report_id):
    with transaction() as db:
        row=db.execute('''SELECT r.*,e.status FROM reports r JOIN report_exports e ON e.report_id=r.id
            WHERE r.id=? AND r.revoked_at IS NULL''',(report_id,)).fetchone()
        if not row or row['status']!='queued':
            return
        db.execute("UPDATE report_exports SET status='running',attempt=attempt+1,updated_at=? WHERE report_id=?",
                   (utc_now(),report_id))
    try:
        payload=_snapshot(row)
        raw=_draw_pdf(payload)
        key=photo_key(row['owner_id'],report_id,f'report-v{_TEMPLATE_VERSION}.pdf')
        checksum=write_asset(key,raw)
        with transaction() as db:
            db.execute('''UPDATE report_exports SET status='complete',template_version=?,pdf_key=?,pdf_sha256=?,
                error_text=NULL,updated_at=? WHERE report_id=? AND status='running' ''',
                (_TEMPLATE_VERSION,key,checksum,utc_now(),report_id))
    except Exception as exc:
        with transaction() as db:
            db.execute("UPDATE report_exports SET status='failed',error_text=?,updated_at=? WHERE report_id=? AND status='running'",
                       (str(exc)[:500],utc_now(),report_id))
