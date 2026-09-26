"""Build the fine-tune dataset (ImageFolder) from frozen benchmarks.

Every image goes through classify.prepare_crop, the exact call used at inference, so the model
trains on what it will see. Labels follow the same rule as the test suite (crop idx N = CSV idx N).
"""
import argparse
import hashlib
import math
import shutil
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from eval import cls, common, pipeline, settings


AUGMENTATIONS = ("blur", "rotate", "warm", "lowl", "overx")
AUGMENT_RANGES = {
    "blur_sigma_px": [1.5, 3.0],
    "rotate_degrees": [-18.0, 18.0],
    "warm_blue_gain": [0.70, 0.85],
    "warm_red_gain": [1.15, 1.30],
    "lowl_gain": [0.50, 0.70],
    "overx_gain": [1.35, 1.65],
}


def augment_crop(image: np.ndarray, kind: str, key: str) -> np.ndarray:
    """Make a reproducible synthetic variant of a prepared training crop."""
    seed = int.from_bytes(hashlib.sha256(f"{key}:{kind}".encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    if kind == "blur":
        sigma = rng.uniform(*AUGMENT_RANGES["blur_sigma_px"])
        return cv2.GaussianBlur(image, (0, 0), sigmaX=sigma, sigmaY=sigma)
    if kind == "rotate":
        angle = rng.uniform(*AUGMENT_RANGES["rotate_degrees"])
        h, w = image.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        cosine, sine = abs(matrix[0, 0]), abs(matrix[0, 1])
        new_w = math.ceil(h * sine + w * cosine)
        new_h = math.ceil(h * cosine + w * sine)
        matrix[0, 2] += (new_w - w) / 2
        matrix[1, 2] += (new_h - h) / 2
        return cv2.warpAffine(image, matrix, (new_w, new_h), borderValue=(0, 0, 0))
    gains = np.ones(3, dtype=np.float32)
    if kind == "warm":
        gains[0] = rng.uniform(*AUGMENT_RANGES["warm_blue_gain"])
        gains[2] = rng.uniform(*AUGMENT_RANGES["warm_red_gain"])
    elif kind == "lowl":
        gains[:] = rng.uniform(*AUGMENT_RANGES["lowl_gain"])
    elif kind == "overx":
        gains[:] = rng.uniform(*AUGMENT_RANGES["overx_gain"])
    else:
        raise ValueError(f"Unknown augmentation: {kind}")
    return np.clip(image.astype(np.float32) * gains, 0, 255).astype(np.uint8)


def write_split(name: str, bench_id: str, split: str, variants: list[str], out: Path,
                checked: set[str] = frozenset(), augment: bool = False) -> dict:
    bench_dir, crops, bmeta = cls.load_bench(bench_id)
    crops = [c for c in crops if c["set"] == split and c["variant"] in variants]
    labels = {k: v for k, v in common.load_labels(settings.LABELS_CSV).items()
              if v[0]["set"] == split and v[0]["variant"] in variants}
    trimmed = {}
    for stem in checked & set(labels):
        # Team checked by eye that crop idx 0..n-1 match CSV idx 0..n-1; drop the extra CSV rows.
        n = sum(c["stem"] == stem for c in crops)
        if 0 < n < len(labels[stem]):
            trimmed[stem] = f"used CSV idx 0-{n - 1}, dropped idx {n}-{len(labels[stem]) - 1} (checked by eye)"
            labels[stem] = labels[stem][:n]
    rows, excluded = cls.join_labels(crops, labels, set())
    for r in rows:
        crop, mask = pipeline.load_bean(bench_dir / "crops" / r["crop"], bench_dir / "masks" / r["mask"], r["mask_kind"])
        d = out / name / r["label"]
        d.mkdir(parents=True, exist_ok=True)
        key = f"{r['stem']}__{r['idx']:02d}"
        image = pipeline.prepare(crop, mask)
        if not cv2.imwrite(str(d / f"{key}.png"), image):
            raise OSError(f"Could not write {d / (key + '.png')}")
        if augment:
            for kind in AUGMENTATIONS:
                if not cv2.imwrite(str(d / f"{key}__{kind}.png"), augment_crop(image, kind, key)):
                    raise OSError(f"Could not write {d / (key + '__' + kind + '.png')}")
    counts = Counter(r["label"] for r in rows)
    print(f"  {name}: {dict(counts)} from {len({r['stem'] for r in rows})} photos, "
          f"{len(rows) * (1 + len(AUGMENTATIONS) if augment else 1)} images, "
          f"{len(excluded)} photo(s) not used {[e['stem'] + ' ' + e['reason'] for e in excluded]}")
    for stem, note in trimmed.items():
        print(f"  {stem}: {note}")
    result = {"bench": bench_id, "split": split, "variants": variants, "counts": dict(counts), "trimmed": trimmed,
              "photos": sorted({r["stem"] for r in rows}), "excluded": excluded,
              "bench_segment_py_sha256": bmeta.get("segment_py_sha256", "")}
    if augment:
        result["augmentation"] = {"variants": list(AUGMENTATIONS), "ranges": AUGMENT_RANGES,
                                  "seed": "first 8 bytes of SHA256(stem__idx:variant)",
                                  "total_images": len(rows) * (1 + len(AUGMENTATIONS)),
                                  "ranges_note": "Chosen estimates; not measured against validation photos"}
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", required=True, help="dataset id, e.g. D1")
    ap.add_argument("--train-bench", default="S0_train")
    ap.add_argument("--val-bench", default=settings.DEFAULT_BENCH)
    ap.add_argument("--val-variants", nargs="+", default=["canon"],
                    help="val images Ultralytics prints during training (monitoring only)")
    ap.add_argument("--checked", nargs="*", default=[],
                    help="photos with fewer crops than labels whose first idx were checked by eye")
    ap.add_argument("--augment", action="store_true",
                    help="add blur, rotate, warm, low-light and overexposed copies to train only")
    args = ap.parse_args()

    # Under data/bench so the photo search skips it (it already ignores BENCH_ROOT).
    out = settings.BENCH_ROOT / "ft" / args.name
    if out.exists():
        raise SystemExit(f"{out} exists; datasets are frozen, use a new --name")
    info = {"name": args.name, "created": common.now(), "git": common.git_info(),
            "labels_csv_sha256": common.sha256(settings.LABELS_CSV),
            "preprocessing": "classify.prepare_crop(crop, mask=mask), same call as inference",
            "classify_py_sha256": common.sha256(settings.CORE / "classify.py"),
            "config_values": {k: v for k, v in pipeline.config_values().items()
                              if k in ("MASK_BACKGROUND_IN_CROP", "GREEN_CAST_G_GAIN", "PAD_MODE", "CLASSIFY_IMGSZ")}}
    try:
        info["train"] = write_split("train", args.train_bench, "train", list(settings.VARIANTS), out,
                                    set(args.checked), augment=args.augment)
        info["val"] = write_split("val", args.val_bench, "val", args.val_variants, out)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    common.write_json(out / "dataset.json", info)
    zip_path = shutil.make_archive(str(out), "zip", out)
    tracked = settings.REPO / "ml" / "finetune" / "records"
    tracked.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out / "dataset.json", tracked / f"{args.name}.json")
    print(f"\nDataset: {out}\nZip for Colab: {zip_path}\nCommit ml/finetune/records/{args.name}.json")


if __name__ == "__main__":
    main()
