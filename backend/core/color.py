"""Colour correction using the paper around a bean as a reference."""

import numpy as np

try:
    from . import config
except ImportError:
    import config


def normalize_to_paper(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    background = bgr[mask == 0]
    keep = (len(background) + 1) // 2
    if keep < config.PAPER_WB_MIN_PIXELS:
        return bgr

    pixels = background.astype(np.float32)
    luminance = pixels @ np.array([0.114, 0.587, 0.299], dtype=np.float32)
    paper = pixels[np.argpartition(luminance, -keep)[-keep:]]
    medians = np.median(paper, axis=0).astype(np.float32)
    gains = np.clip(config.PAPER_WB_TARGET / np.maximum(medians, 1e-6),
                    config.PAPER_WB_GAIN_MIN, config.PAPER_WB_GAIN_MAX).astype(np.float32)
    return np.clip(bgr.astype(np.float32) * gains, 0, 255).astype(np.uint8)
