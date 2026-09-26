import inspect
import sys
from pathlib import Path

import cv2
import numpy as np

from eval import settings

sys.path.insert(0, str(settings.BACKEND))
try:
    from core import classify, config, segment
except ImportError:
    sys.path.insert(0, str(settings.CORE))
    import classify
    import config
    import segment

if classify.config is not config or segment.config is not config:
    raise SystemExit("Backend modules use different config objects; evaluation would ignore config edits")


def check_env(allow_mismatch: bool) -> dict:
    env = {"cv2": cv2.__version__, "numpy": np.__version__, "python": sys.version.split()[0]}
    bad = []
    if env["cv2"] != settings.EXPECTED_CV2:
        bad.append(f"cv2 {env['cv2']} (labels made with {settings.EXPECTED_CV2})")
    if env["numpy"] != settings.EXPECTED_NUMPY:
        bad.append(f"numpy {env['numpy']} (labels made with {settings.EXPECTED_NUMPY})")
    if bad and not allow_mismatch:
        raise SystemExit("Environment differs from the labelling run: " + "; ".join(bad)
                         + "\nUse the same .venv, or pass --allow-env-mismatch if you accept the risk.")
    for b in bad:
        print(f"WARNING: {b}")
    return env


def config_values() -> dict:
    return {k: repr(getattr(config, k)) for k in dir(config) if k.isupper()}


def _count(x) -> int:
    if x is None:
        return 0
    if isinstance(x, (bool, int, np.integer)):
        return int(x)
    try:
        return len(x)
    except TypeError:
        return int(x)


def detect(bgr: np.ndarray, debug: bool = False) -> dict:
    # Same call as main.py, so whatever segment.py/config.py say right now is what runs.
    res = segment.detect_beans(bgr, target_w=config.TARGET_WIDTH, pad=config.CROP_PAD, debug=debug)
    out, flagged, warn, frag, dropped_n, edge_n = res[:6]
    return {
        "beans": out, "flagged": _count(flagged), "warn": str(warn) if warn else "",
        "frag": _count(frag), "dropped_n": _count(dropped_n), "edge_n": _count(edge_n),
        "vis": res[6] if debug and len(res) > 6 else None, "target_w": config.TARGET_WIDTH,
    }


def save_bean(bean: dict, crop_path: Path, mask_path: Path) -> str:
    crop, mask = bean["crop"], np.asarray(bean["mask"])
    if mask.dtype == bool:
        kind, m8 = "bool", mask.astype(np.uint8) * 255
    elif mask.max(initial=0) <= 1:
        kind, m8 = "u8_1", mask.astype(np.uint8) * 255
    else:
        kind, m8 = "u8_255", mask.astype(np.uint8)
    cv2.imwrite(str(crop_path), crop)
    cv2.imwrite(str(mask_path), m8)
    back_crop, back_mask = load_bean(crop_path, mask_path, kind)
    if not (np.array_equal(back_crop, crop) and np.array_equal(back_mask, mask)):
        raise SystemExit(f"Lossless round trip failed for {crop_path.name}")
    return kind


def load_bean(crop_path: Path, mask_path: Path, kind: str) -> tuple[np.ndarray, np.ndarray]:
    crop = cv2.imread(str(crop_path), cv2.IMREAD_UNCHANGED)
    m8 = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    if kind == "bool":
        return crop, m8 > 0
    if kind == "u8_1":
        return crop, (m8 > 0).astype(np.uint8)
    return crop, m8


def prepare(crop: np.ndarray, mask: np.ndarray) -> np.ndarray:
    # Same call as classify_tray, so edits to prepare_crop or config show up here.
    return classify.prepare_crop(crop, mask=mask)


def load_model(path: Path):
    if not path.is_file():
        raise SystemExit(f"Weights not found: {path}")
    if inspect.signature(classify.load_model).parameters:
        model = classify.load_model(str(path))
    else:
        from ultralytics import YOLO
        model = YOLO(str(path))
    names = tuple(model.names[i] for i in sorted(model.names))
    if names != ("fermented", "poorly_fermented"):
        raise SystemExit(f"Unexpected class order in {path.name}: {names}")
    return model


def device_of(model) -> str:
    try:
        return str(next(model.model.parameters()).device)
    except (AttributeError, StopIteration, TypeError):
        return "unknown"


def predict(model, images: list[np.ndarray]) -> list[tuple[str, float, dict]]:
    # Use the production classification path so edits to classify_beans and
    # CLASSIFY_BATCH are reflected in evaluation as well as prepare_crop.
    results = classify.classify_beans(model, images)
    if len(results) != len(images):
        raise RuntimeError(f"Classifier returned {len(results)} predictions for {len(images)} crops")
    return [(r["label"], r["conf"], r["probs"]) for r in results]
