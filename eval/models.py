"""Model backends. Each takes the same benchmark rows and returns one result per bean."""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from eval import common, pipeline, settings

# Changing the wording means a new version, so old runs stay comparable to their own prompt.
PROMPTS = {
    "v1": ("The image shows one cocoa bean cut lengthwise (cut test). "
           "Classify its fermentation as exactly one of: fermented, poorly_fermented. "
           'Reply with JSON only, no other text: {"label": "fermented" or "poorly_fermented", '
           '"confidence": a number from 0 to 1}.'),
}

RETRY_STATUS = {408, 429, 500, 502, 503, 504}


def load_dotenv() -> None:
    env = settings.REPO / "eval" / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.partition("=")
        if sep and not line.lstrip().startswith("#") and not os.environ.get(k.strip()):
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def resolve(spec: str) -> dict:
    if spec in settings.MODEL_ALIASES:
        return {"alias": spec, **settings.MODEL_ALIASES[spec]}
    provider, sep, model_id = spec.partition(":")
    if sep and provider in ("openai", "gemini", "local"):
        if not model_id:
            raise SystemExit(f"--model {spec}: missing model ID after '{provider}:'")
        return {"kind": provider, "model_id": model_id}
    path = Path(spec).expanduser()
    if path.suffix == ".pt":
        return {"kind": "yolo", "weights": path.resolve()}
    raise SystemExit(f"--model {spec}: use an alias {list(settings.MODEL_ALIASES)}, a .pt path, "
                     f"or openai:<id> / gemini:<id> / local:<id>")


# Local YOLO (KakaoLens weights)

def run_yolo(spec: dict, bench_dir: Path, rows: list[dict]) -> tuple[dict, dict]:
    weights = Path(spec["weights"])
    if not weights.is_file():
        raise SystemExit(f"Weights not found: {weights}")
    sha = common.sha256(weights)
    want = spec.get("sha256_prefix")
    if want and not sha.startswith(want):
        raise SystemExit(f"{weights.name} sha256 {sha[:12]} is not the expected {want} for '{spec.get('alias')}'. "
                         f"The file was replaced; point the alias at the original weights.")
    model = pipeline.load_model(weights)
    t0 = time.perf_counter()
    prepared = []
    for r in rows:
        crop, mask = pipeline.load_bean(bench_dir / "crops" / r["crop"], bench_dir / "masks" / r["mask"], r["mask_kind"])
        prepared.append(pipeline.prepare(crop, mask))
    results = pipeline.predict(model, prepared)
    total_ms = (time.perf_counter() - t0) * 1000
    per = total_ms / max(1, len(rows))
    preds = {}
    for r, (label, conf, probs) in zip(rows, results):
        preds[(r["stem"], r["idx"])] = {"pred": label, "status": "ok", "confidence": conf,
                                        "p_fermented": probs.get("fermented", ""), "latency_ms": per,
                                        "attempts": 1, "input_tokens": "", "output_tokens": "", "cost_usd": 0.0,
                                        "raw_output": "", "error": ""}
    info = {
        "kind": "yolo", "weights": str(weights), "weights_sha256": sha, "device": pipeline.device_of(model),
        "input": "classify.prepare_crop(crop, mask=mask), the same call classify_tray makes",
        "preprocessing_config": {k: v for k, v in pipeline.config_values().items()
                                 if k in ("MASK_BACKGROUND_IN_CROP", "GREEN_CAST_G_GAIN", "PAD_MODE", "CLASSIFY_IMGSZ")},
        "cost_note": "API cost 0 (runs locally). Hardware and energy cost not measured.",
        "compute_ms_total": round(total_ms, 1), "compute_ms_per_bean": round(per, 2),
        "latency_note": "batched crop prep + predict divided by number of beans; model load excluded",
    }
    return preds, info


# API models

def _encode(bench_dir: Path, r: dict, masked: bool) -> tuple[str, tuple[int, int]]:
    crop, mask = pipeline.load_bean(bench_dir / "crops" / r["crop"], bench_dir / "masks" / r["mask"], r["mask_kind"])
    img = crop.copy()
    if masked:
        img[np.asarray(mask) == 0] = 0
    ok, buf = cv2.imencode(".png", img)
    return base64.b64encode(buf.tobytes()).decode(), (img.shape[1], img.shape[0])


def _post(url: str, headers: dict, body: dict, timeout: float) -> tuple[int, dict | None, str]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode()
            return resp.status, json.loads(text), text
    except urllib.error.HTTPError as e:
        return e.code, None, e.read().decode(errors="replace")[:500]
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, None, f"{type(e).__name__}: {e}"


def parse_answer(text: str) -> tuple[str, float | str]:
    m = re.search(r"\{.*?\}", text or "", re.S)
    if not m:
        return "invalid", ""
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return "invalid", ""
    try:
        label = common.norm_label(str(obj.get("label", "")))
    except ValueError:
        label = None
    if label not in common.BINARY:
        return "invalid", ""
    try:
        conf = float(obj.get("confidence"))
    except (TypeError, ValueError):
        conf = ""
    return label, conf


def _chat_call(base: str, key: str | None, model_id: str, prompt: str, b64: str, timeout: float):
    body = {"model": model_id, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    status, data, raw = _post(f"{base}/chat/completions", headers, body, timeout)
    if data is None:
        return status, None, None, None, raw
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return status, None, None, None, json.dumps(data)[:500]
    u = data.get("usage") or {}
    return status, text, u.get("prompt_tokens"), u.get("completion_tokens"), ""


def _gemini_call(base: str, key: str, model_id: str, prompt: str, b64: str, timeout: float):
    body = {"contents": [{"role": "user", "parts": [
        {"text": prompt}, {"inline_data": {"mime_type": "image/png", "data": b64}}]}]}
    status, data, raw = _post(f"{base}/models/{model_id}:generateContent", {"x-goog-api-key": key}, body, timeout)
    if data is None:
        return status, None, None, None, raw
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        return status, None, None, None, json.dumps(data)[:500]
    u = data.get("usageMetadata") or {}
    out_tokens = (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)
    return status, text, u.get("promptTokenCount"), out_tokens, ""


def run_api(spec: dict, bench_dir: Path, rows: list[dict], prompt_version: str, masked: bool,
            workers: int, price: tuple[float, float] | None, endpoint: str | None, timeout: float) -> tuple[dict, dict]:
    load_dotenv()
    kind, model_id = spec["kind"], spec["model_id"]
    prompt = PROMPTS[prompt_version]
    if kind == "openai":
        base, key = endpoint or settings.OPENAI_BASE_URL, os.environ.get("OPENAI_API_KEY")
        call = _chat_call
    elif kind == "gemini":
        base, key = endpoint or settings.GEMINI_BASE_URL, os.environ.get("GEMINI_API_KEY")
        call = _gemini_call
    else:
        base, key = endpoint or settings.LOCAL_BASE_URL, os.environ.get("LOCAL_API_KEY")
        call = _chat_call
    if kind in ("openai", "gemini") and not key:
        raise SystemExit(f"{'OPENAI_API_KEY' if kind == 'openai' else 'GEMINI_API_KEY'} is not set (env or .env)")
    local = kind == "local"

    def scrub(value: str) -> str:
        # A provider error may echo request details. Never persist the credential.
        return value.replace(key, "[REDACTED]") if key else value

    sizes = []

    def one(r: dict) -> tuple[tuple, dict]:
        b64, size = _encode(bench_dir, r, masked)
        sizes.append(size)
        last_err, attempts = "", 0
        started = time.perf_counter()
        for attempts in range(1, 4):
            status, text, tin, tout, err = call(base, key, model_id, prompt, b64, timeout)
            if text is not None or status not in RETRY_STATUS and status != 0:
                break
            last_err = f"HTTP {status}: {err}" if status else err
            if attempts < 3:
                time.sleep(2 ** attempts)
        if text is None:
            res = {"pred": "error", "status": "error", "confidence": "", "raw_output": "",
                   "error": scrub(last_err or (f"HTTP {status}: {err}" if status else err))}
        else:
            label, conf = parse_answer(text)
            res = {"pred": label, "status": "ok" if label in common.BINARY else "invalid", "confidence": conf,
                   "raw_output": scrub(text.replace("\n", " "))[:300], "error": ""}
        if local:
            cost = 0.0
        elif price and tin is not None and tout is not None:
            cost = (tin * price[0] + tout * price[1]) / 1e6
        else:
            cost = ""
        res.update({"p_fermented": "", "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    "input_tokens": tin if tin is not None else "",
                    "output_tokens": tout if tout is not None else "", "cost_usd": cost, "attempts": attempts})
        return (r["stem"], r["idx"]), res

    preds = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for k, res in ex.map(one, rows):
            preds[k] = res

    ws = sorted(s[0] for s in sizes)
    hs = sorted(s[1] for s in sizes)
    info = {
        "kind": kind, "model_id": model_id, "endpoint": scrub(base), "prompt_version": prompt_version,
        "prompt_text": prompt, "workers": workers, "timeout_s": timeout, "retries": "up to 3 attempts on 408/429/5xx/network",
        "input": ("raw crop from the benchmark, " + ("background set to black with the segmenter mask"
                  if masked else "background not masked") + ", no colour gain, lossless PNG, native crop size "
                  f"(median {ws[len(ws) // 2] if ws else '-'}x{hs[len(hs) // 2] if hs else '-'} px)"),
        "price_usd_per_1m_tokens": list(price) if price else None,
        "cost_note": ("API cost 0 (local endpoint); local GPU time is in latency, hardware and energy cost not measured"
                      if local else ("cost = tokens x configured price" if price else
                                     "price not configured, so no cost is reported")),
        "latency_note": "wall time of all HTTP attempts and retry waits per bean; calls run in parallel, so per-bean latency is not throughput",
    }
    return preds, info
