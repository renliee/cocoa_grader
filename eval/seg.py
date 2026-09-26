import time
from pathlib import Path

import cv2

from eval import common, draw, pipeline, settings

PHOTO_FIELDS = ["stem", "set", "variant", "sheet", "detected", "expected", "diff"]


def expected_counts() -> dict[str, int]:
    if not settings.GT_COUNTS_CSV.exists():
        return {}
    return {Path(r["filename"]).stem: common.to_int(r["gt_count"]) for r in common.read_csv(settings.GT_COUNTS_CSV)}


def run(args, run_path: Path) -> dict:
    images = {s: p for s, p in common.list_images(settings.IMAGES_DIR).items()
              if (m := common.parse_name(s)) and m[0] == args.split and m[1] in settings.VARIANTS}
    if args.limit:
        images = dict(sorted(images.items())[:args.limit])
    if not images:
        raise SystemExit(f"No '{args.split}' photos under {settings.IMAGES_DIR}")
    exp = expected_counts()
    rows, ms = [], []
    for stem, path in sorted(images.items()):
        s, v, sh = common.parse_name(stem)
        bgr = cv2.imread(str(path))
        t0 = time.perf_counter()
        res = pipeline.detect(bgr)
        ms.append((time.perf_counter() - t0) * 1000)
        e = exp.get(stem, settings.GT_COUNT)
        n = len(res["beans"])
        rows.append({"stem": stem, "set": s, "variant": v, "sheet": str(int(sh)), "detected": n, "expected": e,
                     "diff": n - e})
        if not args.no_annotate and (n != e or args.annotate_all):
            vis = pipeline.detect(bgr, debug=True)["vis"]
            if vis is not None:
                draw.save(run_path / "annotated" / f"{stem}.jpg", vis)
        print(f"  {stem:<18} {n:>2}/{e}")

    per_v = []
    for v in [*settings.VARIANTS, "ALL"]:
        rs = rows if v == "ALL" else [r for r in rows if r["variant"] == v]
        if rs:
            per_v.append({"variant": v, "photos": len(rs), "detected": sum(r["detected"] for r in rs),
                          "expected": sum(r["expected"] for r in rs),
                          "photos_exact": sum(r["diff"] == 0 for r in rs)})
    common.write_csv(run_path / "per_photo.csv", rows, PHOTO_FIELDS)
    common.write_csv(run_path / "predictions.csv", rows, PHOTO_FIELDS)
    common.write_csv(run_path / "failures.csv", [r for r in rows if r["diff"]], PHOTO_FIELDS)
    common.write_csv(run_path / "per_variant.csv", per_v)
    common.write_csv(run_path / "summary.csv", per_v)

    code = common.snapshot(run_path, ["segment.py", "config.py"])
    cfg = {"task": "segmentation", "run": args.run, "split": args.split, "created": common.now(),
           "git": common.git_info(), "env": pipeline.check_env(True), "code": code,
           "config_values": pipeline.config_values(), "images_dir": str(settings.IMAGES_DIR),
           "expected_source": "gt_counts.csv" if exp else f"{settings.GT_COUNT} beans per photo",
           "ms_per_photo_mean": round(sum(ms) / len(ms), 1), "limit": args.limit,
           "summary": per_v[-1]}
    common.write_json(run_path / "run_config.json", cfg)

    L = [f"# Segmentation {args.run} ({args.split})", "",
         "- code: " + ", ".join(f"{k} {v['sha256'][:12]}" for k, v in code.items()),
         f"- git: {cfg['git']['head'][:10]}{' (dirty)' if cfg['git']['dirty'] else ''}, created {cfg['created']}",
         f"- expected count: {cfg['expected_source']}",
         f"- time: {cfg['ms_per_photo_mean']} ms per photo (segmentation only, this machine)"]
    if args.limit:
        L.append(f"- PARTIAL RUN: first {args.limit} photos only")
    L += ["", "| variant | photos | detected / expected | photos exact |", "|---|---|---|---|"]
    L += [f"| {p['variant']} | {p['photos']} | {p['detected']}/{p['expected']} | {p['photos_exact']}/{p['photos']} |"
          for p in per_v]
    off = [r for r in rows if r["diff"]]
    if off:
        L += ["", "## Photos where detected != expected", "", "| photo | detected / expected |", "|---|---|"]
        L += [f"| {r['stem']} | {r['detected']}/{r['expected']} |" for r in off]
    (run_path / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    a = per_v[-1]
    return {"detail": f"segment.py {code['segment.py']['sha256'][:12]}",
            "headline": f"detected {a['detected']}/{a['expected']} | exact photos {a['photos_exact']}/{a['photos']}"}
