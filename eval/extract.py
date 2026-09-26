"""Build a frozen crop benchmark: run segment.py once per photo and cache every crop losslessly.

Classification runs read only this cache, so every model is scored on the same beans.
Run it once per benchmark id; it refuses to overwrite.
"""
import argparse
import shutil
from collections import Counter
from pathlib import Path

import cv2

from eval import common, pipeline, settings

BEAN_FIELDS = ["stem", "set", "variant", "sheet", "idx", "label", "x0", "y0", "w", "h",
               "cx", "cy", "area", "ar", "crop", "mask", "mask_kind"]
IMAGE_FIELDS = ["stem", "file", "set", "variant", "sheet", "sha256", "source_w", "source_h", "target_w",
                "detected", "label_rows", "count_ok", "held"]


def extract(bench_id: str, images: dict[str, Path], labels: dict[str, list[dict]],
            meta: dict[str, tuple[str, str, str]], hold: set[str] | None = None,
            hold_mismatch: bool = False, force: bool = False) -> tuple[Path, list[dict], list[dict], list[str]]:
    out = settings.BENCH_ROOT / bench_id
    if out.exists():
        if not force:
            raise SystemExit(f"Benchmark {bench_id} already exists at {out}. It is frozen; use a new id.")
        shutil.rmtree(out)
    (out / "crops").mkdir(parents=True)
    (out / "masks").mkdir()

    beans, imgs, errors = [], [], []
    for stem in sorted(set(labels) - set(images)):
        errors.append(f"{stem}: has label rows but no image")

    for stem in sorted(images):
        path = images[stem]
        bgr = cv2.imread(str(path))
        if bgr is None:
            errors.append(f"{stem}: cv2 could not read {path.name}")
            continue
        res = pipeline.detect(bgr)
        rows = labels.get(stem, [])
        s, v, sh = meta[stem]
        ok = len(res["beans"]) == len(rows)
        held = ""
        if hold and stem in hold:
            held = "manual hold"
        elif not ok and hold_mismatch:
            held = "count mismatch"
        elif not ok:
            errors.append(f"{stem}: detected {len(res['beans'])} beans, label CSV has {len(rows)} rows")
        n_rows = len(rows)
        if held:
            rows = []
        imgs.append({"stem": stem, "file": str(path.relative_to(settings.REPO)) if path.is_relative_to(settings.REPO)
                     else str(path), "set": s, "variant": v, "sheet": sh, "sha256": common.sha256(path),
                     "source_w": bgr.shape[1], "source_h": bgr.shape[0], "target_w": res["target_w"],
                     "detected": len(res["beans"]), "label_rows": n_rows, "count_ok": ok, "held": held})
        for i, b in enumerate(res["beans"]):
            crop_name, mask_name = f"{stem}__{i:02d}.png", f"{stem}__{i:02d}_mask.png"
            kind = pipeline.save_bean(b, out / "crops" / crop_name, out / "masks" / mask_name)
            x0, y0, w, h = (int(t) for t in b["bbox"])
            beans.append({"stem": stem, "set": s, "variant": v, "sheet": sh, "idx": i,
                          "label": rows[i]["label"] if i < len(rows) else "",
                          "x0": x0, "y0": y0, "w": w, "h": h, "cx": round(x0 + w / 2, 1), "cy": round(y0 + h / 2, 1),
                          "area": float(b.get("area", w * h)), "ar": float(b.get("ar", 0.0)),
                          "crop": crop_name, "mask": mask_name, "mask_kind": kind})
        print(f"  {stem:<18} detected {len(res['beans']):>2}  labels {n_rows:>2}  "
              f"{'OK' if ok else 'MISMATCH'}{'  HELD (' + held + ')' if held else ''}")
    return out, beans, imgs, errors


def finish(bench_id: str, out: Path, beans: list[dict], imgs: list[dict], errors: list[str],
           env: dict, extra: dict) -> dict:
    meta = {
        "bench_id": bench_id, "created": common.now(), "status": "OK" if not errors else "FAILED",
        "errors": errors, "git": common.git_info(), "env": env,
        "code": common.snapshot(out, ["segment.py", "config.py"]),
        "segment_py_sha256": common.sha256(settings.CORE / "segment.py"),
        "config_py_sha256": common.sha256(settings.CORE / "config.py"),
        "target_w": pipeline.config.TARGET_WIDTH, "pad": pipeline.config.CROP_PAD,
        "n_images": len(imgs), "n_beans": len(beans), **extra,
    }
    common.write_csv(out / "manifest.csv", beans, BEAN_FIELDS)
    common.write_csv(out / "images.csv", imgs, IMAGE_FIELDS)
    common.write_json(out / "metadata.json", meta)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bench", required=True, help="new benchmark id, e.g. S1")
    ap.add_argument("--sets", nargs="+", default=list(settings.SETS), choices=list(settings.SETS))
    ap.add_argument("--images", type=Path, default=settings.IMAGES_DIR)
    ap.add_argument("--labels", type=Path, default=settings.LABELS_CSV)
    ap.add_argument("--hold", nargs="*", default=[], help="photo stems to keep out for manual checking")
    ap.add_argument("--allow-env-mismatch", action="store_true")
    args = ap.parse_args()

    env = pipeline.check_env(args.allow_env_mismatch)
    labels = {k: v for k, v in common.load_labels(args.labels).items() if v[0]["set"] in args.sets}
    images, meta = {}, {}
    for stem, path in common.list_images(args.images).items():
        p = common.parse_name(stem)
        if p and p[1] in settings.VARIANTS and p[0] in args.sets:
            images[stem], meta[stem] = path, (p[0], p[1], str(int(p[2])))
    print(f"{len(images)} images, {sum(len(r) for r in labels.values())} label rows")

    out, beans, imgs, errors = extract(args.bench, images, labels, meta, set(args.hold), hold_mismatch=True)
    m = finish(args.bench, out, beans, imgs, errors, env,
               {"sets": args.sets, "images_dir": str(args.images), "labels_csv": str(args.labels),
                "labels_sha256": common.sha256(args.labels), "label_rule": "crop idx N = CSV idx N of the same photo",
                "held": {i["stem"]: i["held"] for i in imgs if i["held"]}})

    tracked = settings.TRACKED_BENCH / args.bench
    tracked.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.csv", "images.csv", "metadata.json"):
        shutil.copy2(out / name, tracked / name)
    shutil.copytree(out / "code_snapshot", tracked / "code_snapshot", dirs_exist_ok=True)

    bal = Counter((b["set"], b["variant"], b["label"] or "unlabelled") for b in beans)
    print("\nClass balance (fermented / poorly_fermented / unlabelled):")
    for s in args.sets:
        for v in settings.VARIANTS:
            f, pf, u = (bal[(s, v, k)] for k in ("fermented", "poorly_fermented", "unlabelled"))
            if f or pf or u:
                print(f"  {s:<6}{v:<8}{f:>4}{pf:>5}{u:>5}")
    full = [i for i in imgs if i["detected"] == settings.GT_COUNT == i["label_rows"] and not i["held"]]
    print(f"\nPhotos with {settings.GT_COUNT} crops and {settings.GT_COUNT} label rows: {len(full)} of {len(imgs)}")
    for i in imgs:
        if i not in full:
            print(f"  {i['stem']}: {i['detected']} crops, {i['label_rows']} label rows"
                  f"{'  HELD (' + i['held'] + ')' if i['held'] else ''}")
    if errors:
        print("\nFAILED:")
        for e in errors:
            print(f"  {e}")
        raise SystemExit(1)
    print(f"\nOK. {m['n_beans']} crops from {m['n_images']} photos in {out}. Commit {tracked}")


if __name__ == "__main__":
    main()
