"""
main.py: HTTP layer. The only file in the backend that imports FastAPI.
Every files  inside core/ stays framework free so the pipeline can be run and tested from a terminal. 
This file does three things : decode uploads, run the pipeline, shape the response.

Can receive multiple photos per request. One sheet of paper holds roughly 15 beans while keeping the spacing the segmenter needs, 
and the cut test requires more than 15 beans to provide a representative sample.
"""
import base64
import os
from contextlib import asynccontextmanager
from typing import Annotated, List

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile as _UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import WithJsonSchema
from core import classify, config, grade, segment

#fix Swagger's file upload button for newer FastAPI versions, Without this, /docs wont show the file picker
UploadFile = Annotated[_UploadFile, WithJsonSchema({"type": "string", "format": "binary"})]
    
WEIGHTS_PATH = os.environ.get("KAKAO_WEIGHTS", "weights/best.pt") #update: can receive env variables from docker

#upload limits and max picture size of the FastAPI
MAX_FILES = 40
MAX_FILE_BYTES = 10 * 1024 * 1024

#annotated photo returned to the browser. 1280 keeps labels readable in a screen recording, base64 inflates the payload by a third.
ANNOTATED_WIDTH = 1280
ANNOTATED_JPEG_QUALITY = 80

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
    #they're explained via catatan_rincian text instead (a box here read as a false artifact).

    #set the width of annonated img to fixed size before sending it back to the browser
    ch, cw = canvas.shape[:2]
    if cw > ANNOTATED_WIDTH:
        s = ANNOTATED_WIDTH / cw
        canvas = cv2.resize(canvas, (ANNOTATED_WIDTH, int(ch * s)), interpolation=cv2.INTER_AREA)

    ok, buf = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, ANNOTATED_JPEG_QUALITY]) #compress the annotated image 
    if not ok:
        raise HTTPException(500, "Gagal mengenkode gambar hasil.")
    return base64.b64encode(buf.tobytes()).decode() #encode the annotated image as a base64 string so it can be sent in JSON


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
        "jumlah_kelas": {c: labels.count(c) for c in config.CLASS_NAMES},
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

    hasil = grade.grade(semua_label, n_unreadable=total_unreadable, n_photos=len(files))

    #Segmentation warnings sit above grading warnings rather than beside them. If detection is unreliable then the unreadable counts feeding grade() are
    #unreliable too, which means the range itself rests on shaky inputs. The frontend should treat this as a blocker, not a footnote.
    blocking = [f"Hasil analisis pada “{p['nama']}” perlu diperhatikan. Terdapat banyak bagian kecil yang tidak dapat dihitung sebagai biji, sehingga kemungkinan terdapat biji pecah atau tidak terhitung."
                for p in per_foto if p["segmentasi_curiga"]]
    blocking += [f"Tidak ada biji yang terdeteksi pada “{n}”." for n in kosong]

    return {
        "ringkasan": hasil,
        "laporan": grade.format_report(hasil),
        "per_foto": per_foto,
        "blocking_warning": blocking,
    }