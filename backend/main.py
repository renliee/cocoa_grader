"""
main.py: HTTP layer. The only file in the backend that imports FastAPI.
Every files  inside core/ stays framework free so the pipeline can be run and tested from a terminal. 
This file does three things : decode uploads, run the pipeline, shape the response.

Can receive multiple photos per request. One sheet of paper holds roughly 30 beans while keeping the spacing the segmenter needs, and 30 beans is 
not enough to place a batch against a narrow SNI thresholds. grade() never learns how many photos were involved, it receives one merged list of labels.
"""
import os
from contextlib import asynccontextmanager
from typing import Annotated, List

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile as _UploadFile
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import WithJsonSchema
from core import classify, config, grade, segment

#fix Swagger's file upload button for newer FastAPI versions, Without this, /docs wont show the file picker
UploadFile = Annotated[_UploadFile, WithJsonSchema({"type": "string", "format": "binary"})]
    
WEIGHTS_PATH = "weights/best.pt"

#upload limits and max picture size of the FastAPI
MAX_FILES = 10
MAX_FILE_BYTES = 12 * 1024 * 1024

_model = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load the classifier model once at startup (fast failure always better than silent failure).
    Loading per request would add seconds of latency to every call and would also delay a class name mismatch until a user hits the endpoint. 
    """
    _model["clf"] = classify.load_model(WEIGHTS_PATH)
    yield
    _model.clear() #clear model on shutdown


app = FastAPI(
    title="KakaoLens API",
    description="Klasifikasi tingkat fermentasi biji kakao dari foto nampan.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


def _decode(raw, name):
    """Convert bytes from image to BGR array. A file that fails to decode is raised"""
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR) #decode the bytes into a BGR array, so that opencv can process it.
    if img is None:
        raise HTTPException(400, f"'{name}' bukan gambar yang valid dibaca. Kirim dalam JPG atau PNG.")
    return img


def _count_unreadable(flagged, dropped_n, edge_n):
    """
    Count beans that reached the tray but could not be classified. Count the estimated number of beans in each unsplit cluster, 
    not the number of clusters. Include dropped and edge beans in the total.
    """
    return sum(f["est_beans"] for f in flagged) + dropped_n + edge_n


def _analyze_one(img, name):
    """Run one photo through segmentation and classification."""
    beans, flagged, warn, frag, dropped_n, edge_n = segment.detect_beans(img, target_w=config.TARGET_WIDTH, pad=config.CROP_PAD)

    hasil = classify.classify_tray(_model["clf"], beans) if beans else []
    labels = [h["label"] for h in hasil]
    n_unreadable = _count_unreadable(flagged, dropped_n, edge_n)

    laporan = {
        "nama": name,
        "biji_terbaca": len(labels),
        "biji_tidak_terbaca": n_unreadable,
        "gumpalan": len(flagged),
        "serpihan": dropped_n,
        "kena_tepi": edge_n,
        "luas_terbuang": round(100 * frag, 1),
        "segmentasi_curiga": bool(warn),
        "jumlah_kelas": {c: labels.count(c) for c in classify.EXPECTED_CLASSES},
    }

    #shows the highest probability of slaty beans in the tray, rounded to 4 decimal places. This is used to determine if the tray is "slaty" or not.
    if hasil:
        laporan["p_slaty_maks"] = round(max(h["probs"]["slaty"] for h in hasil), 4)

    return labels, n_unreadable, laporan


@app.get("/api/health")
async def health():
    """Reports whether the model is loaded"""
    return {"status": "ok", "model": "clf" in _model}


@app.post("/api/analyze")   
async def analyze(files: List[UploadFile] = File(...)):
    """
    One or more tray photos in, one grading result out.
    Labels from every photo are pooled before grading. Perphoto detail is
    returned alongside so a user can tell which photo caused a warning.
    """
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maksimal {MAX_FILES} foto per permintaan, dikirim {len(files)}.")

    semua_label, total_unreadable, per_foto = [], 0, []

    for f in files:
        raw = await f.read() #read file and save it as a bytes object. 
        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(400, f"'{f.filename}' lebih dari {MAX_FILE_BYTES // (1024 * 1024)} MB.")

        labels, n_unread, laporan = _analyze_one(_decode(raw, f.filename),f.filename)
        semua_label += labels
        total_unreadable += n_unread
        per_foto.append(laporan)

    #photo with nothing in it is reported, not silently treated as zero beans, because an empty sheet and a failed detection look identical in the totals.
    kosong = [p["nama"] for p in per_foto if p["biji_terbaca"] == 0]

    if not semua_label:
        raise HTTPException(422, "Tidak ada biji yang terbaca di foto manapun. Periksa jarak antar biji dan pastikan kertas alas tidak mepet tepi foto.")

    hasil = grade.grade(semua_label, n_unreadable=total_unreadable)

    #Segmentation warnings sit above grading warnings rather than beside them. If detection is unreliable then the unreadable counts feeding grade() are
    #unreliable too, which means the range itself rests on shaky inputs. The frontend should treat this as a blocker, not a footnote.
    blocking = [f"Segmentasi mencurigakan di '{p['nama']}'. Banyak serpihan terbuang, kemungkinan ada biji yang pecah dan tidak terhitung."
                for p in per_foto if p["segmentasi_curiga"]]
    blocking += [f"Tidak ada biji terdeteksi di '{n}'." for n in kosong]

    return {
        "ringkasan": hasil,
        "laporan": grade.format_report(hasil),
        "per_foto": per_foto,
        "blocking_warning": blocking,
    }

#ENDPOINT BELOW IS FOR DEBUG PURPOSE ONLY, NOT PART OF THE COMPETITION MVP. 

# @app.post("/api/debug/visualize")
# async def debug_visualize(file: UploadFile = File(...)):
#     """
#     A developer tool, not part of the MVP competition. Perform segmentation and classification on a single photo and return the annotated image directly, 
#     rather than JSON, so that the segmentation/classification quality can be visually inspected without opening VSCode.
#     """
#     raw = await file.read()
#     img = _decode(raw, file.filename)

#     beans, flagged, warn, frag, dropped_n, edge_n = segment.detect_beans(img, target_w=config.TARGET_WIDTH, pad=config.CROP_PAD)

#     hasil = classify.classify_tray(_model["clf"], beans) if beans else []

#     h, w = img.shape[:2]
#     if w != config.TARGET_WIDTH:
#         s = config.TARGET_WIDTH / w
#         canvas = cv2.resize(img, (config.TARGET_WIDTH, int(h * s)), interpolation=cv2.INTER_AREA)
#     else:
#         canvas = img.copy()

#     COLORS = {
#         "fermented": (0, 200, 0),
#         "slaty": (0, 0, 255),
#         "under_fermented": (0, 255, 255),
#         "violet": (255, 0, 255),
#     }
#     FLAGGED_COLOR = (255, 255, 0)

#     for i, (bean, h_) in enumerate(zip(beans, hasil)):
#         x, y, bw, bh = bean["bbox"]
#         label = h_["label"]
#         color = COLORS.get(label, (255, 255, 255))
#         cv2.rectangle(canvas, (x, y), (x + bw, y + bh), color, 2)
#         cv2.putText(canvas, f"{i} {label}", (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

#     for f in flagged:
#         x, y, bw, bh = f["bbox"]
#         cv2.rectangle(canvas, (x, y), (x + bw, y + bh), FLAGGED_COLOR, 3)
#         cv2.putText(canvas, f"?x{f['est_beans']}", (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, FLAGGED_COLOR, 2, cv2.LINE_AA)

#     ok, buf = cv2.imencode(".jpg", canvas)
#     if not ok:
#         raise HTTPException(500, "Gagal mengenkode gambar hasil.")
#     return Response(content=buf.tobytes(), media_type="image/jpeg")