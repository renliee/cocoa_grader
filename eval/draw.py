from pathlib import Path

import cv2
import numpy as np

# Same colours as main.py/_annotate (BGR).
COLOR = {"fermented": (0, 200, 0), "poorly_fermented": (0, 0, 255)}
WRONG = (0, 215, 255)
SHORT = {"fermented": "F", "poorly_fermented": "PF", "defect": "D", "skip": "S", "none": "-"}


def tile(img: np.ndarray, lines: list[str], size: int = 140) -> np.ndarray:
    h, w = img.shape[:2]
    s = size / max(h, w)
    small = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    t = np.full((size + 16 * len(lines), size, 3), 255, np.uint8)
    y0, x0 = (size - small.shape[0]) // 2, (size - small.shape[1]) // 2
    t[y0:y0 + small.shape[0], x0:x0 + small.shape[1]] = small
    for i, line in enumerate(lines):
        cv2.putText(t, line, (3, size + 12 + 16 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1, cv2.LINE_AA)
    return t


def sheet(tiles: list[np.ndarray], cols: int = 8) -> np.ndarray:
    th = max(t.shape[0] for t in tiles)
    tw = max(t.shape[1] for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    out = np.full((rows * (th + 4), cols * (tw + 4), 3), 230, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        out[r * (th + 4):r * (th + 4) + t.shape[0], c * (tw + 4):c * (tw + 4) + t.shape[1]] = t
    return out


def overlay(src: np.ndarray, target_w: int, boxes: list[dict]) -> np.ndarray:
    # bboxes live in the resized space detect_beans works in, so resize the canvas the same way.
    h, w = src.shape[:2]
    canvas = cv2.resize(src, (target_w, int(round(h * target_w / w))))
    for b in boxes:
        x, y, bw, bh = b["bbox"]
        cv2.rectangle(canvas, (x, y), (x + bw, y + bh), b["color"], b.get("thick", 3))
        cv2.putText(canvas, b["text"], (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    b["color"], 2, cv2.LINE_AA)
    return canvas


def save(path: Path, img: np.ndarray, max_w: int = 1400) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if img.shape[1] > max_w:
        img = cv2.resize(img, (max_w, int(img.shape[0] * max_w / img.shape[1])), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 88] if path.suffix == ".jpg" else [])
