"""
main.py: HTTP layer. The only file in the backend that imports FastAPI.
Every files  inside core/ stays framework free so the pipeline can be run and tested from a terminal. 
This file does three things : decode uploads, run the pipeline, shape the response.

Can receive multiple photos per request. One sheet of paper holds roughly 15 beans while keeping the spacing the segmenter needs, 
and the cut test requires more than 15 beans to provide a representative sample.
"""
import base64
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Annotated, List

try:
    import cv2
    import numpy as np
except ModuleNotFoundError:
    if os.environ.get('KAKAO_SKIP_MODEL_LOAD') != '1':
        raise
    cv2 = None
    np = None
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile as _UploadFile
from fastapi.responses import JSONResponse
from pydantic import WithJsonSchema
from core import config, grade
from db import migrate
import domain
import reports
import security
from schemas import SignupIn, LoginIn, ProfilePatch, SupplierIn, SupplierPatch, LotIn, DraftPatch, PhotoReview, ExpectedInput, AnalyzeIn, FinalizeIn, LotVersionIn
from storage import delete_photo_assets

if os.environ.get('KAKAO_SKIP_MODEL_LOAD') != '1':
    from core import classify, segment
else:
    classify = segment = None

if cv2 is not None:
    import workflow
else:
    workflow = None

#fix Swagger's file upload button for newer FastAPI versions, Without this, /docs wont show the file picker
UploadFile = Annotated[_UploadFile, WithJsonSchema({"type": "string", "format": "binary"})]
    
WEIGHTS_PATH = os.environ.get("KAKAO_WEIGHTS", "weights/best.pt") #update: can receive env variables from docker

#upload limits and max picture size of the FastAPI
MAX_FILES = 50
MAX_FILE_BYTES = 10 * 1024 * 1024

#annotated photo returned to the browser. 1280 keeps labels readable in a screen recording, base64 inflates the payload by a third.
ANNOTATED_WIDTH = 1280
ANNOTATED_JPEG_QUALITY = 80

#logger formatter
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

class _SkipHealth(logging.Filter):
    """Omit repetitive health checks and bearer report tokens from access logs."""
    def filter(self, record):
        message = record.getMessage()
        return '/api/health' not in message and '/api/reports/' not in message


def _setup_logging():
    """
    Uvicorn only configures its own loggers and leaves the root logger empty, so a new logger would fall through to
    lastResort at WARNING level and every INFO line would vanish with no error. Configure root here, then restamp
    uvicorn's handlers with the same format because its default access line carries no timestamp at all.
    """
    #WIB is UTC+7, staticmethod is required, a bare function assigned on the class would bind and receive self.
    logging.Formatter.converter = staticmethod(lambda secs: time.gmtime(secs + 7 * 3600))
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=DATE_FORMAT) 
    fmt = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for h in logging.getLogger(name).handlers:
            h.setFormatter(fmt)
    logging.getLogger("uvicorn.access").addFilter(_SkipHealth()) #ignore healthcheck 


_setup_logging()
log = logging.getLogger("kakaolens") 

def _ringkas_kelas(nilai, satuan=""):
    """Class values in the wording the browser uses, so the log and the screen can be read side by side."""
    return ", ".join(f"{grade.LABEL_ID[c].lower()} {nilai[c]}{satuan}" for c in config.CLASS_NAMES)

_model = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load the classifier model once at startup (fast failure always better than silent failure).
    Loading per request would add seconds of latency to every call and would also delay a class name mismatch until a user hits the endpoint. 
    """
    migrate()
    if classify is not None:
        t0 = time.perf_counter() #track the time before loading the model (to count the ms later)
        _model["clf"] = classify.load_model(WEIGHTS_PATH)
        #report the classes the loaded model actually carries, not the ones config expects, so the line is evidence rather than an echo
        names = _model["clf"].names
        log.info("model dimuat: %s | kelas %s | %.0f ms", WEIGHTS_PATH, tuple(names[i] for i in sorted(names)), 1000 * (time.perf_counter() - t0))
    if workflow is not None:
        workflow.start_worker(_model.get('clf'))
    reports.start_worker()
    yield
    reports.stop_worker()
    if workflow is not None:
        workflow.stop_worker()
    _model.clear() #clear model on shutdown
    log.info("model dilepas, backend berhenti")


app = FastAPI(
    title="KakaoLens API",
    description="Classify cocoa bean fermentation from tray photos.",
    lifespan=lifespan,
)

# Authenticated routes are served through the same-origin frontend proxy.


def _origin_ok(request: Request):
    origin = request.headers.get('origin')
    if origin:
        from urllib.parse import urlsplit
        parsed = urlsplit(origin)
        expected_scheme = request.headers.get('x-forwarded-proto', request.url.scheme)
        if parsed.scheme != expected_scheme or parsed.netloc.lower() != request.headers.get('host', '').lower():
            raise HTTPException(403, 'This request origin is not allowed.')


def _report_origin(request: Request):
    scheme = request.headers.get('x-forwarded-proto', request.url.scheme)
    if scheme not in ('http', 'https'):
        raise HTTPException(400, 'Invalid request protocol.')
    return f"{scheme}://{request.headers.get('host', '')}"


def _current(request: Request):
    session = security.get_session(request.cookies.get('kl_session'))
    if not session:
        raise HTTPException(401, 'Please sign in again.')
    return session


def _write(request: Request, session=Depends(_current)):
    _origin_ok(request)
    if not security.check_csrf(session, request.headers.get('x-csrf-token')):
        raise HTTPException(403, 'Your security session has changed. Refresh the page.')
    return session


def _session_response(request: Request, user):
    token, csrf = security.create_session(user['id'])
    response = JSONResponse({'user': user, 'csrf_token': csrf})
    response.set_cookie('kl_session', token, httponly=True, samesite='lax',
                        secure=os.environ.get('KAKAO_ALLOW_HTTP_COOKIES') != '1',
                        max_age=security.SESSION_DAYS * 86400, path='/')
    return response


@app.exception_handler(domain.DomainError)
async def domain_error(_request: Request, exc: domain.DomainError):
    return JSONResponse({'detail': str(exc)}, status_code=exc.status)


@app.post('/api/auth/signup')
def signup(request: Request, body: SignupIn):
    _origin_ok(request)
    if body.password != body.password_confirmation:
        raise HTTPException(400, 'Passwords do not match.')
    return _session_response(request, domain.signup(body.display_name, body.login, body.password))


@app.post('/api/auth/login')
def login(request: Request, body: LoginIn):
    _origin_ok(request)
    return _session_response(request, domain.login(body.login, body.password))


@app.get('/api/auth/me')
def me(session=Depends(_current)):
    return {'user': {key: session[key] for key in ('id', 'login', 'display_name', 'timezone')},
            'csrf_token': session['csrf_token']}


@app.patch('/api/account/profile')
def profile_update(body: ProfilePatch, session=Depends(_write)):
    return domain.update_profile(session['id'], body.display_name)


@app.post('/api/auth/logout')
def logout(request: Request, session=Depends(_write)):
    security.revoke_session(request.cookies.get('kl_session'))
    response = JSONResponse({'ok': True})
    response.delete_cookie('kl_session', path='/')
    return response


@app.get('/api/suppliers')
def suppliers(include_archived: bool = False, session=Depends(_current)):
    return {'items': domain.list_suppliers(session['id'], include_archived)}


@app.get('/api/suppliers/{supplier_id}/performance')
def supplier_performance(supplier_id: str, session=Depends(_current)):
    return domain.supplier_performance(session['id'], supplier_id)


@app.post('/api/suppliers', status_code=201)
def supplier_create(body: SupplierIn, session=Depends(_write)):
    return domain.create_supplier(session['id'], body.name, body.code, body.contact, body.notes)


@app.patch('/api/suppliers/{supplier_id}')
def supplier_update(supplier_id: str, body: SupplierPatch, session=Depends(_write)):
    return domain.update_supplier(session['id'], supplier_id, body.name, body.contact, body.notes)


@app.post('/api/suppliers/{supplier_id}/archive')
def supplier_archive(supplier_id: str, session=Depends(_write)):
    return domain.archive_supplier(session['id'], supplier_id, True)


@app.post('/api/suppliers/{supplier_id}/restore')
def supplier_restore(supplier_id: str, session=Depends(_write)):
    return domain.archive_supplier(session['id'], supplier_id, False)


@app.delete('/api/suppliers/{supplier_id}')
def supplier_delete(supplier_id: str, session=Depends(_write)):
    return domain.delete_supplier(session['id'], supplier_id)


@app.post('/api/lots', status_code=201)
def lot_create(body: LotIn, session=Depends(_write)):
    return domain.create_lot(session['id'], body.supplier_id)


@app.get('/api/drafts')
def drafts(session=Depends(_current)):
    return {'items': domain.list_drafts(session['id'])}


@app.get('/api/lots')
def lots(session=Depends(_current)):
    return {'items': domain.list_finalized_lots(session['id'])}


@app.get('/api/lots/{lot_id}')
def lot_detail(lot_id: str, session=Depends(_current)):
    if workflow is None:
        raise HTTPException(503, 'Analysis results are unavailable on this server.')
    return workflow.result_for_lot(session['id'], lot_id)


@app.get('/api/lots/{lot_id}/revisions')
def lot_revisions(lot_id: str, session=Depends(_current)):
    return domain.list_revisions(session['id'], lot_id)


@app.post('/api/lots/{lot_id}/revisions')
def lot_revise(lot_id: str, body: LotVersionIn, session=Depends(_write)):
    return domain.begin_revision(session['id'], lot_id, body.expected_lot_version)


@app.get('/api/lots/{lot_id}/revisions/{revision_id}')
def revision_detail(lot_id: str, revision_id: str, session=Depends(_current)):
    if workflow is None:
        raise HTTPException(503, 'Analysis results are unavailable on this server.')
    return workflow.result_for_revision(session['id'], lot_id, revision_id)


@app.post('/api/lots/{lot_id}/revisions/{revision_id}/activate')
def revision_activate(lot_id: str, revision_id: str, body: LotVersionIn, session=Depends(_write)):
    return domain.activate_revision(session['id'], lot_id, revision_id, body.expected_lot_version)


@app.post('/api/lots/{lot_id}/revisions/{revision_id}/report')
def report_create(lot_id: str, revision_id: str, request: Request, session=Depends(_write)):
    return reports.create_report(session['id'], lot_id, revision_id, _report_origin(request))


@app.post('/api/lots/{lot_id}/revisions/{revision_id}/report/pdf/retry')
def report_pdf_retry(lot_id: str, revision_id: str, session=Depends(_write)):
    return reports.retry_pdf(session['id'], lot_id, revision_id)


@app.get('/api/reports/{token}')
def public_report(token: str, request: Request):
    return JSONResponse(reports.get_report(token, _report_origin(request)), headers={'Referrer-Policy': 'no-referrer',
                                                            'Cache-Control': 'no-store'})


@app.get('/api/reports/{token}/photos/{photo_id}')
def public_report_photo(token: str, photo_id: str):
    return Response(reports.report_photo(token, photo_id), media_type='image/jpeg',
                    headers={'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store'})


@app.get('/api/reports/{token}/pdf')
def public_report_pdf(token: str):
    return Response(reports.report_pdf(token), media_type='application/pdf',
                    headers={'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store',
                             'Content-Disposition': f'attachment; filename="KakaoLens-{token[:12]}.pdf"'})


@app.get('/api/reports/{token}/qr')
def public_report_qr(token: str, request: Request):
    return Response(reports.report_qr(token, _report_origin(request)), media_type='image/png',
                    headers={'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store'})


@app.get('/api/drafts/{draft_id}')
def draft_get(draft_id: str, session=Depends(_current)):
    return domain.get_draft(session['id'], draft_id)


@app.delete('/api/drafts/{draft_id}')
def draft_delete(draft_id: str, session=Depends(_write)):
    deleted = domain.delete_draft(session['id'], draft_id)
    for photo_id in deleted['orphaned_photo_ids']:
        delete_photo_assets(session['id'], photo_id)
    for run_id in deleted['run_ids']:
        delete_photo_assets(session['id'], run_id)
    return {'deleted': True}


@app.patch('/api/drafts/{draft_id}')
def draft_patch(draft_id: str, body: DraftPatch, session=Depends(_write)):
    return domain.update_draft(session['id'], draft_id, body.expected_version,
                               body.weight_kg, body.notes, body.wizard_step,
                               body.supplier_id if 'supplier_id' in body.model_fields_set else domain.UNSET)


@app.get('/api/dashboard')
def dashboard(period: str = '30d', session=Depends(_current)):
    return domain.dashboard(session['id'], period)


@app.post('/api/drafts/{draft_id}/analyze', status_code=202)
def draft_analyze(draft_id: str, body: AnalyzeIn, session=Depends(_write)):
    if workflow is None or classify is None or 'clf' not in _model:
        raise HTTPException(503, 'The analysis model is unavailable on this server.')
    return workflow.start_analysis(session['id'], draft_id, body.expected_input_version,
                                   body.confirm_small_sample)


@app.get('/api/drafts/{draft_id}/result')
def draft_result(draft_id: str, session=Depends(_current)):
    if workflow is None:
        raise HTTPException(503, 'Analysis results are unavailable on this server.')
    return workflow.result_for_draft(session['id'], draft_id)


@app.post('/api/drafts/{draft_id}/finalize')
def draft_finalize(draft_id: str, body: FinalizeIn, session=Depends(_write)):
    saved = domain.finalized_receipt(session['id'], draft_id)
    if saved:
        return saved
    if workflow is None:
        raise HTTPException(503, 'Analysis results are unavailable on this server.')
    workflow.verify_finalizable(session['id'], draft_id, body.expected_version)
    return domain.finalize_draft(session['id'], draft_id, body.expected_version)


@app.get('/api/runs/{run_id}/photos/{photo_id}/image')
def result_photo_asset(run_id: str, photo_id: str, session=Depends(_current)):
    if workflow is None:
        raise HTTPException(503, 'Analysis results are unavailable on this server.')
    payload, media_type = workflow.result_image(session['id'], run_id, photo_id)
    return Response(payload, media_type=media_type, headers={'Cache-Control': 'private, no-store'})


@app.post('/api/drafts/{draft_id}/photos', status_code=201)
async def photo_upload(draft_id: str, file: UploadFile = File(...),
                       upload_key: str = Header(alias='Idempotency-Key'), session=Depends(_write)):
    if workflow is None:
        raise HTTPException(503, 'Photo processing is unavailable on this server.')
    raw = await file.read(workflow.MAX_FILE_BYTES + 1)
    return workflow.upload_photo(session['id'], draft_id, file.filename or 'foto', raw, upload_key)


@app.put('/api/drafts/{draft_id}/photos/{photo_id}')
async def photo_replace(draft_id: str, photo_id: str, file: UploadFile = File(...),
                        upload_key: str = Header(alias='Idempotency-Key'), session=Depends(_write)):
    if workflow is None:
        raise HTTPException(503, 'Photo processing is unavailable on this server.')
    raw = await file.read(workflow.MAX_FILE_BYTES + 1)
    return workflow.replace_photo(session['id'], draft_id, photo_id,
                                  file.filename or 'foto', raw, upload_key)


@app.delete('/api/drafts/{draft_id}/photos/{photo_id}')
def photo_delete(draft_id: str, photo_id: str, session=Depends(_write)):
    if workflow is None:
        raise HTTPException(503, 'Photo processing is unavailable on this server.')
    return workflow.delete_draft_photo(session['id'], draft_id, photo_id)


@app.get('/api/drafts/{draft_id}/photos')
def photos(draft_id: str, session=Depends(_current)):
    if workflow is None:
        raise HTTPException(503, 'Photo processing is unavailable on this server.')
    items = workflow.list_photos(session['id'], draft_id)
    return {'items': items, 'summary': workflow.photo_summary(items)}


@app.delete('/api/drafts/{draft_id}/photos')
def photos_clear(draft_id: str, body: ExpectedInput, session=Depends(_write)):
    if workflow is None:
        raise HTTPException(503, 'Photo processing is unavailable on this server.')
    return workflow.clear_draft_photos(session['id'], draft_id, body.expected_input_version)


@app.get('/api/drafts/{draft_id}/photos/{photo_id}/image/{kind}')
def photo_asset(draft_id: str, photo_id: str, kind: str, session=Depends(_current)):
    if workflow is None:
        raise HTTPException(503, 'Photo processing is unavailable on this server.')
    payload, media_type = workflow.photo_image(session['id'], draft_id, photo_id, kind)
    return Response(payload, media_type=media_type, headers={'Cache-Control': 'private, no-store'})


@app.patch('/api/drafts/{draft_id}/photos/{photo_id}')
def photo_review(draft_id: str, photo_id: str, body: PhotoReview, session=Depends(_write)):
    if workflow is None:
        raise HTTPException(503, 'Photo processing is unavailable on this server.')
    return workflow.review_photo(session['id'], draft_id, photo_id,
                                 body.expected_input_version, body.review_state)


@app.post('/api/drafts/{draft_id}/photos/use-all')
def photos_use_all(draft_id: str, body: ExpectedInput, session=Depends(_write)):
    if workflow is None:
        raise HTTPException(503, 'Photo processing is unavailable on this server.')
    return workflow.use_all_ready(session['id'], draft_id, body.expected_input_version)


@app.post('/api/drafts/{draft_id}/photos/{photo_id}/retry')
def photo_retry(draft_id: str, photo_id: str, session=Depends(_write)):
    if workflow is None:
        raise HTTPException(503, 'Photo processing is unavailable on this server.')
    return workflow.retry_precheck(session['id'], draft_id, photo_id)


def _decode(raw, name):
    """Convert bytes from image to BGR array. A file that fails to decode is raised"""
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR) #decode the bytes into a BGR array, so that opencv can process it.
    if img is None:
        raise HTTPException(400, f"'{name}' is not a readable image. Upload a JPEG or PNG file.")
    return img


def _count_unreadable(flagged, dropped_n, edge_n):
    """
    Count beans that reached the tray but could not be classified. Count the estimated number of beans in each unsplit cluster, 
    not the number of clusters. Include dropped and edge beans in the total.
    """
    return sum(f["est_beans"] for f in flagged) + dropped_n + edge_n


def _annotate(img, beans, hasil):
    """
    Draw the detections on the photo so a user can check the count against the beans in front of them.
    Drawn from the same detection pass that produced the labels, so the picture and the numbers will always aligned.
    Line and font sizes are set for the downscale below, otherwise the labels vanish under video compression.
    """
    #resize to the target width to ensure the labels are readable and the coordinate system matches the detection output, because we trained the model on a fixed width.
    h, w = img.shape[:2]
    if w != config.TARGET_WIDTH:
        s = config.TARGET_WIDTH / w
        canvas = cv2.resize(img, (config.TARGET_WIDTH, int(h * s)), interpolation=cv2.INTER_AREA)
    else:
        canvas = img.copy()

    #determine the bounding box color for each label.
    COLORS = {
        "fermented": (0, 200, 0), #green
        "poorly_fermented": (0, 0, 255), #red
    }
    for i, (bean, h_) in enumerate(zip(beans, hasil)):
        x, y, bw, bh = bean["bbox"]
        color = COLORS.get(h_["label"], (255, 255, 255)) #white as a fallback
        cv2.rectangle(canvas, (x, y), (x + bw, y + bh), color, 3) #draw bounding box around the bean, with px of 3
        ty = y - 8 if y > 22 else y + bh + 24 #if the box is too close to the top of the image, draw the label below it instead of above it.
        cv2.putText(canvas, f"{i} {grade.LABEL_ID[h_['label']]}", (x, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA) #put the label on the image

    #clusters the splitter could not resolve are intentionally not boxed on the image;
    #they're explained via catatan_rincian text instead.

    #set the width of annonated img to fixed size before sending it back to the browser
    ch, cw = canvas.shape[:2]
    if cw > ANNOTATED_WIDTH:
        s = ANNOTATED_WIDTH / cw
        canvas = cv2.resize(canvas, (ANNOTATED_WIDTH, int(ch * s)), interpolation=cv2.INTER_AREA)

    ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, ANNOTATED_JPEG_QUALITY]) #compress the annotated image 
    if not ok:
        raise HTTPException(500, "Unable to encode the result image.")
    return base64.b64encode(buf.tobytes()).decode() #encode the annotated image as a base64 string so it can be sent in JSON


def _analyze_one(img, name):
    """Run one photo through segmentation and classification."""
    t0 = time.perf_counter() #t0 here is used to track the ms
    beans, flagged, warn, frag, dropped_n, edge_n = segment.detect_beans(img, target_w=config.TARGET_WIDTH, pad=config.CROP_PAD)
    t_seg = time.perf_counter() - t0

    t1 = time.perf_counter()
    hasil = classify.classify_tray(_model["clf"], beans) if beans else []
    t_clf = time.perf_counter() - t1

    labels = [h["label"] for h in hasil]
    jumlah_kelas = {c: labels.count(c) for c in config.CLASS_NAMES}
    n_unreadable = _count_unreadable(flagged, dropped_n, edge_n)

    #the numbers on these two lines are the same ones the browser will show, so a viewer can check the log against the screen
    log.info("segmentasi  %4.0f ms | %d terbaca, %d gumpalan, %d serpihan, %d kena tepi", 1000 * t_seg, len(beans), len(flagged), dropped_n, edge_n)
    log.info("klasifikasi %4.0f ms | %s", 1000 * t_clf, _ringkas_kelas(jumlah_kelas))

    laporan = {
        "nama": name,
        "biji_terbaca": len(labels),
        "biji_tidak_terbaca": n_unreadable,
        "gumpalan": len(flagged),
        "serpihan": dropped_n,
        "kena_tepi": edge_n,
        "luas_terbuang": round(100 * frag, 1),
        "segmentasi_curiga": bool(warn),
        "jumlah_kelas": jumlah_kelas,
    }

    #shows the min and max probability of fermented beans in the tray, rounded to 4 decimal places. 
    if hasil:
        pf = [h["probs"]["fermented"] for h in hasil]
        laporan["p_fermented_min"] = round(min(pf), 4)
        laporan["p_fermented_maks"] = round(max(pf), 4)

    laporan["gambar"] = _annotate(img, beans, hasil)

    return labels, n_unreadable, laporan


@app.get("/api/health")
async def health():
    """Reports whether the model is loaded, used by docker healthcheck"""
    return {"status": "ok", "model": "clf" in _model}


@app.post("/api/analyze")   
async def analyze(files: List[UploadFile] = File(...)):
    """
    One or more tray photos in, one grading result out.
    Labels from every photo are pooled before grading. Perphoto detail is
    returned alongside so a user can tell which photo caused a warning.
    """
    if classify is None or 'clf' not in _model:
        raise HTTPException(503, 'The analysis model is unavailable on this server.')
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maximum {MAX_FILES} photos per request; {len(files)} received.")

    t_req = time.perf_counter()
    log.info("permintaan analisis diterima, %d photos", len(files))

    semua_label, total_unreadable, per_foto = [], 0, []

    for i, f in enumerate(files, 1):
        raw = await f.read() #read file and save it as a bytes object. 
        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(400, f"'{f.filename}' exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB.")

        log.info("[%d/%d] %s", i, len(files), f.filename) #to show every photo number index
        labels, n_unread, laporan = _analyze_one(_decode(raw, f.filename), f.filename)
        semua_label += labels
        total_unreadable += n_unread
        per_foto.append(laporan)

    #photo with nothing in it is reported, not silently treated as zero beans, because an empty sheet and a failed detection look identical in the totals.
    kosong = [p["nama"] for p in per_foto if p["biji_terbaca"] == 0]

    if not semua_label:
        raise HTTPException(422, "No cocoa beans were detected. Leave space between beans and keep the entire paper background in the photo.")

    hasil = grade.grade(semua_label, n_unreadable=total_unreadable, n_photos=len(files))

    #Segmentation warnings sit above grading warnings rather than beside them. If detection is unreliable then the unreadable counts feeding grade() are
    #unreliable too, which means the range itself rests on shaky inputs. The frontend should treat this as a blocker, not a footnote.
    blocking = [f"Review the result for “{p['nama']}”. Many small fragments were excluded, so some beans may be broken or uncounted."
                for p in per_foto if p["segmentasi_curiga"]]
    blocking += [f"No beans were detected in “{n}”." for n in kosong]

    #warning level so a blocked result stands out from the routine lines instead of scrolling past unnoticed
    for b in blocking:
        log.warning("perlu diperhatikan: %s", b)
    
    log.info("ringkasan %d photos | %d beans terbaca, %d tidak terbaca", len(files), len(semua_label), total_unreadable) #summary of all photos classified in numbers
    log.info("hasil | %s | total %.0f ms", _ringkas_kelas(hasil["persen"], "%"), 1000 * (time.perf_counter() - t_req)) #summary of all photos classified in percent
    
    return {
        "ringkasan": hasil,
        "laporan": grade.format_report(hasil),
        "per_foto": per_foto,
        "blocking_warning": blocking,
    }
