"""Build the fine-tune dataset (ImageFolder) from frozen benchmarks.

Every image goes through classify.prepare_crop, the exact call used at inference, so the model
trains on what it will see. Labels follow the same rule as the test suite (crop idx N = CSV idx N).
"""
import argparse
import shutil
from collections import Counter
from pathlib import Path

import cv2

from eval import cls, common, pipeline, settings


def write_split(name: str, bench_id: str, split: str, variants: list[str], out: Path,
                checked: set[str] = frozenset()) -> dict:
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
        cv2.imwrite(str(d / f"{r['stem']}__{r['idx']:02d}.png"), pipeline.prepare(crop, mask))
    counts = Counter(r["label"] for r in rows)
    print(f"  {name}: {dict(counts)} from {len({r['stem'] for r in rows})} photos, "
          f"{len(excluded)} photo(s) not used {[e['stem'] + ' ' + e['reason'] for e in excluded]}")
    for stem, note in trimmed.items():
        print(f"  {stem}: {note}")
    return {"bench": bench_id, "split": split, "variants": variants, "counts": dict(counts), "trimmed": trimmed,
            "photos": sorted({r["stem"] for r in rows}), "excluded": excluded,
            "bench_segment_py_sha256": bmeta.get("segment_py_sha256", "")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", required=True, help="dataset id, e.g. D1")
    ap.add_argument("--train-bench", default="S0_train")
    ap.add_argument("--val-bench", default=settings.DEFAULT_BENCH)
    ap.add_argument("--val-variants", nargs="+", default=["canon"],
                    help="val images Ultralytics prints during training (monitoring only)")
    ap.add_argument("--checked", nargs="*", default=[],
                    help="photos with fewer crops than labels whose first idx were checked by eye")
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
                                    set(args.checked))
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
