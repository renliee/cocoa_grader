import json
from collections import Counter
from pathlib import Path

import cv2

from eval import common, draw, models, pipeline, settings
from eval.common import BINARY

PREDS = ("fermented", "poorly_fermented", "invalid", "error")
SHORT = {"fermented": "F", "poorly_fermented": "PF", "invalid": "INV", "error": "ERR"}
PRED_FIELDS = ["stem", "set", "variant", "sheet", "idx", "label", "pred", "correct", "status", "confidence",
               "p_fermented", "latency_ms", "attempts", "input_tokens", "output_tokens", "cost_usd", "raw_output", "error"]


def load_bench(bench_id: str) -> tuple[Path, list[dict], dict]:
    out = settings.BENCH_ROOT / bench_id
    if not (out / "metadata.json").exists():
        raise SystemExit(f"No benchmark at {out}. Build it once with: python -m eval.extract --bench {bench_id}")
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    if meta["status"] != "OK":
        raise SystemExit(f"Benchmark {bench_id} status is {meta['status']}: {meta['errors'][:5]}")
    rows = common.read_csv(out / "manifest.csv")
    for r in rows:
        r["idx"] = int(r["idx"])
        for k in ("x0", "y0", "w", "h"):
            r[k] = int(r[k])
    return out, rows, meta


def join_labels(crops: list[dict], labels: dict[str, list[dict]], exclude: set[str]) -> tuple[list[dict], list[dict]]:
    """Crop idx N gets CSV label idx N of the same photo. Photos whose counts differ are listed, not guessed."""
    by_stem: dict[str, list[dict]] = {}
    for c in crops:
        by_stem.setdefault(c["stem"], []).append(c)
    scored, excluded = [], []
    other = Counter()
    for stem in sorted(set(by_stem) | set(labels)):
        cs, ls = by_stem.get(stem, []), labels.get(stem, [])
        if stem in exclude:
            excluded.append({"stem": stem, "crops": len(cs), "label_rows": len(ls), "reason": "--exclude"})
        elif len(cs) != len(ls):
            excluded.append({"stem": stem, "crops": len(cs), "label_rows": len(ls), "reason": "count mismatch"})
        elif sorted(c["idx"] for c in cs) != [lab["idx"] for lab in ls]:
            excluded.append({"stem": stem, "crops": len(cs), "label_rows": len(ls), "reason": "idx mismatch"})
        else:
            for c, lab in zip(sorted(cs, key=lambda x: x["idx"]), ls):
                if lab["label"] in BINARY:
                    scored.append({**c, "label": lab["label"]})
                else:
                    other[lab["label"]] += 1
    if other:
        excluded.append({"stem": "(all)", "crops": sum(other.values()), "label_rows": sum(other.values()),
                         "reason": f"label not fermented/poorly_fermented: {dict(other)}"})
    return scored, excluded


def metrics(rows: list[dict], preds: dict) -> dict:
    cm = Counter((r["label"], preds[(r["stem"], r["idx"])]["pred"]) for r in rows)
    n = len(rows)
    m = {"n": n, "correct": sum(cm[(c, c)] for c in BINARY)}
    m["accuracy"] = m["correct"] / n if n else None
    recalls = []
    for c in BINARY:
        s = SHORT[c]
        n_true = sum(cm[(c, p)] for p in PREDS)
        n_pred = sum(cm[(t, c)] for t in BINARY)
        tp = cm[(c, c)]
        rec = tp / n_true if n_true else None
        prec = tp / n_pred if n_pred else None
        m.update({f"n_{s}": n_true, f"tp_{s}": tp, f"recall_{s}": rec, f"precision_{s}": prec,
                  f"f1_{s}": 2 * rec * prec / (rec + prec) if rec and prec else (0.0 if rec is not None and prec is not None else None)})
        recalls.append(rec)
    m["balanced_accuracy"] = sum(recalls) / 2 if None not in recalls else None
    ps = [preds[(r["stem"], r["idx"])] for r in rows]
    m["invalid"] = sum(p["status"] == "invalid" for p in ps)
    m["error"] = sum(p["status"] == "error" for p in ps)
    m["confident_wrong"] = sum(1 for r, p in zip(rows, ps) if p["pred"] in BINARY and p["pred"] != r["label"]
                               and p["confidence"] != "" and float(p["confidence"]) >= settings.CONFIDENT_WRONG)
    lat = sorted(float(p["latency_ms"]) for p in ps if p["latency_ms"] != "")
    m["latency_ms_mean"] = sum(lat) / len(lat) if lat else None
    m["latency_ms_p50"] = lat[len(lat) // 2] if lat else None
    m["latency_ms_p95"] = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None
    costs = [p["cost_usd"] for p in ps]
    m["cost_usd"] = sum(costs) if costs and all(c != "" for c in costs) else None
    m["input_tokens"] = sum(int(p["input_tokens"]) for p in ps if p["input_tokens"] != "") or None
    m["output_tokens"] = sum(int(p["output_tokens"]) for p in ps if p["output_tokens"] != "") or None
    m["confusion"] = {f"{SHORT[t]}->{SHORT[p]}": cm[(t, p)] for t in BINARY for p in PREDS}
    return m


def by_variant(rows: list[dict]) -> list[tuple[str, list[dict]]]:
    groups = [(v, [r for r in rows if r["variant"] == v]) for v in settings.VARIANTS]
    return [(v, rs) for v, rs in groups if rs] + [("ALL", rows)]


def compare(rows: list[dict], preds: dict, parent_run: str, bench_id: str, labels_sha: str) -> list[dict]:
    pdir = settings.RESULTS / "classification" / parent_run
    cfg = json.loads((pdir / "run_config.json").read_text(encoding="utf-8"))
    if cfg["benchmark"]["id"] != bench_id or cfg["labels"]["sha256"] != labels_sha:
        raise SystemExit(f"{parent_run} used a different benchmark or label CSV, so beans are not comparable")
    parent = {(r["stem"], int(r["idx"])): r["pred"] for r in common.read_csv(pdir / "predictions.csv")}
    out = []
    for v, rs in by_variant(rows):
        fixed = broken = 0
        for r in rs:
            a = parent.get((r["stem"], r["idx"])) == r["label"]
            b = preds[(r["stem"], r["idx"])]["pred"] == r["label"]
            fixed += b and not a
            broken += a and not b
        out.append({"variant": v, "fixed": fixed, "broken": broken, "net_fixed": fixed - broken})
    return out


def f(x, d: int = 3) -> str:
    return common.fmt(x, d)


def write_report(run: Path, cfg: dict, table: list[dict], all_m: dict, excluded: list[dict],
                 cmp: list[dict] | None) -> None:
    mi = cfg["model"]
    name = mi.get("model_id") or Path(mi.get("weights", "")).name
    L = [f"# Classification {cfg['run']} ({cfg['split']})", "",
         f"- model: {mi['kind']} `{name}`" + (f" sha256 {mi['weights_sha256'][:12]}" if mi.get("weights_sha256") else ""),
         f"- input: {mi['input']}"]
    if mi.get("prompt_version"):
        L.append(f"- prompt: {mi['prompt_version']}")
    if mi.get("preprocessing_config"):
        L.append(f"- preprocessing config: {mi['preprocessing_config']}")
    L += [f"- benchmark: {cfg['benchmark']['id']} (crops cut with segment.py sha256 "
          f"{cfg['benchmark']['segment_py_sha256'][:12]}), labels sha256 {cfg['labels']['sha256'][:12]}",
          f"- label rule: {cfg['labels']['rule']}",
          "- code: " + ", ".join(f"{k} {v['sha256'][:12]}" for k, v in cfg["code"].items()),
          f"- git: {cfg['git']['head'][:10]}{' (dirty)' if cfg['git']['dirty'] else ''}, created {cfg['created']}"]
    if cfg.get("limit"):
        L.append(f"- PARTIAL RUN: first {cfg['limit']} beans only, not comparable to full runs")
    L += ["", "| variant | beans | BA | F recall / precision | PF recall / precision |",
          "|---|---|---|---|---|"]
    for t in table:
        L.append(f"| {t['variant']} | {t['n']} | {f(t['balanced_accuracy'])} "
                 f"| {t['tp_F']}/{t['n_F']} = {f(t['recall_F'])} / {f(t['precision_F'])} "
                 f"| {t['tp_PF']}/{t['n_PF']} = {f(t['recall_PF'])} / {f(t['precision_PF'])} |")
    c = all_m["confusion"]
    L += ["", "## Confusion matrix (all variants; rows = label)", "", "| label \\ pred | F | PF |",
          "|---|---|---|"]
    for t in ("F", "PF"):
        L.append(f"| {t} | {c[f'{t}->F']} | {c[f'{t}->PF']} |")
    L += ["", "Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.", "",
          "## Latency and cost", "",
          f"- latency per bean: mean {f(all_m['latency_ms_mean'], 1)} ms, p50 {f(all_m['latency_ms_p50'], 1)} ms, "
          f"p95 {f(all_m['latency_ms_p95'], 1)} ms ({mi['latency_note']})"]
    if mi.get("device"):
        L.append(f"- device: {mi['device']}")
    if all_m["input_tokens"] or all_m["output_tokens"]:
        L.append(f"- tokens: {all_m['input_tokens']} in, {all_m['output_tokens']} out")
    L.append(f"- cost: {'$' + f(all_m['cost_usd'], 4) if all_m['cost_usd'] is not None else 'not reported'} "
             f"({mi['cost_note']})")
    if excluded:
        L += ["", "## Photos not scored", "", "| photo | crops | label rows | reason |", "|---|---|---|---|"]
        L += [f"| {e['stem']} | {e['crops']} | {e['label_rows']} | {e['reason']} |" for e in excluded]
    if cmp:
        L += ["", f"## Versus {cfg['compare_to']} (same beans)", "", "| variant | fixed | broken | net fixed |",
              "|---|---|---|---|"]
        L += [f"| {x['variant']} | {x['fixed']} | {x['broken']} | {x['net_fixed']} |" for x in cmp]
        net = cmp[-1]["net_fixed"]
        L.append(f"\nVerdict: {'BETTER' if net >= settings.IMPROVE_NET_FIXED else 'NOT BETTER'} "
                 f"(net {net} beans, rule >= {settings.IMPROVE_NET_FIXED})")
    (run / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def annotate(run: Path, bench_dir: Path, rows: list[dict], preds: dict) -> None:
    ann = run / "annotated"
    for v, rs in by_variant(rows)[:-1]:
        tiles = []
        for r in rs:
            p = preds[(r["stem"], r["idx"])]
            if p["pred"] != r["label"]:
                conf = f" {float(p['confidence']):.2f}" if p["confidence"] != "" else ""
                img = cv2.imread(str(bench_dir / "crops" / r["crop"]))
                tiles.append(draw.tile(img, [f"{r['stem'].split('_', 1)[-1]} #{r['idx']}",
                                             f"GT {SHORT[r['label']]} -> {SHORT.get(p['pred'], p['pred'])}{conf}"]))
        if tiles:
            draw.save(ann / f"failures_{v}.png", draw.sheet(tiles[:96]), max_w=1600)
    images = common.list_images(settings.IMAGES_DIR)
    tw = {r["stem"]: int(r["target_w"]) for r in common.read_csv(bench_dir / "images.csv")}
    photos: dict[str, list[dict]] = {}
    for r in rows:
        photos.setdefault(r["stem"], []).append(r)
    for stem, rs in photos.items():
        boxes, wrong = [], 0
        for r in rs:
            p = preds[(r["stem"], r["idx"])]
            bad = p["pred"] != r["label"]
            wrong += bad
            color = draw.WRONG if bad else draw.COLOR[p["pred"]]
            boxes.append({"bbox": (r["x0"], r["y0"], r["w"], r["h"]), "color": color, "thick": 5 if bad else 2,
                          "text": f"{r['idx']} GT:{SHORT[r['label']]}" if bad else str(r["idx"])})
        src = cv2.imread(str(images[stem])) if wrong and stem in images else None
        if src is not None:
            draw.save(ann / f"{stem}.jpg", draw.overlay(src, tw[stem], boxes))


def run(args, run_path: Path) -> dict:
    spec = models.resolve(args.model)
    bench_dir, crops, bmeta = load_bench(args.bench)
    labels_sha = common.sha256(args.labels)
    if bmeta.get("labels_sha256") and labels_sha != bmeta["labels_sha256"]:
        raise SystemExit("Label CSV differs from the frozen benchmark metadata; use matching labels and crops")
    crops = [c for c in crops if c["set"] == args.split]
    if not crops:
        raise SystemExit(f"Benchmark {args.bench} has no '{args.split}' crops")
    labels = {k: v for k, v in common.load_labels(args.labels).items() if v[0]["set"] == args.split}
    rows, excluded = join_labels(crops, labels, set(args.exclude))
    if args.limit:
        rows = rows[:args.limit]

    if spec["kind"] == "yolo":
        preds, minfo = models.run_yolo(spec, bench_dir, rows)
    else:
        if args.prompt not in models.PROMPTS:
            raise SystemExit(f"Unknown --prompt {args.prompt}; known: {list(models.PROMPTS)}")
        price = settings.PRICES.get(spec["model_id"])
        if args.price_in is not None or args.price_out is not None:
            if args.price_in is None or args.price_out is None:
                raise SystemExit("Give both --price-in and --price-out")
            price = (args.price_in, args.price_out)
        preds, minfo = models.run_api(spec, bench_dir, rows, args.prompt, not args.unmasked,
                                      args.workers, price, args.endpoint, args.timeout)

    pred_rows, fails = [], []
    for r in rows:
        p = preds[(r["stem"], r["idx"])]
        row = {**{k: r[k] for k in ("stem", "set", "variant", "sheet", "idx", "label")}, **p,
               "correct": p["pred"] == r["label"]}
        for k in ("confidence", "p_fermented"):
            if isinstance(row[k], float):
                row[k] = round(row[k], 4)
        if isinstance(row["cost_usd"], float):
            row["cost_usd"] = round(row["cost_usd"], 6)
        pred_rows.append(row)
        if not row["correct"]:
            fails.append(row)
    common.write_csv(run_path / "predictions.csv", pred_rows, PRED_FIELDS)
    common.write_csv(run_path / "failures.csv", fails, PRED_FIELDS)

    table = []
    for v, rs in by_variant(rows):
        m = metrics(rs, preds)
        table.append({"variant": v, **m})

    cmp = compare(rows, preds, args.compare, args.bench, labels_sha) if args.compare else None
    if cmp:
        common.write_csv(run_path / "compare.csv", cmp)

    code = common.snapshot(run_path, ["segment.py", "classify.py", "config.py"])
    seg_sha = bmeta.get("segment_py_sha256", "")
    cfg = {
        "task": "classification", "run": args.run, "split": args.split, "created": common.now(),
        "git": common.git_info(), "env": pipeline.check_env(True),
        "model": minfo,
        "benchmark": {"id": args.bench, "manifest_sha256": common.sha256(bench_dir / "manifest.csv"),
                      "segment_py_sha256": seg_sha, "built_at_git": bmeta.get("git", {}).get("head", ""),
                      "built": bmeta.get("created", "")},
        "labels": {"csv": str(args.labels), "sha256": labels_sha,
                   "rule": "crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling"},
        "code": code,
        "code_notes": {
            "segment.py": ("same file that cut the benchmark crops" if code["segment.py"]["sha256"] == seg_sha else
                           "DIFFERS from the file that cut the crops; crops come from the benchmark, not this file"),
            "classify.py": "used (prepare_crop and classify_beans)" if minfo["kind"] == "yolo" else "not used by this model",
            "config.py": "used" if minfo["kind"] == "yolo" else "not used by this model",
        },
        "n_beans": len(rows), "excluded_photos": excluded, "limit": args.limit, "compare_to": args.compare,
        "summary": {k: v for k, v in table[-1].items() if k != "variant"},
    }
    common.write_json(run_path / "run_config.json", cfg)
    write_report(run_path, cfg, table, table[-1], excluded, cmp)
    if not args.no_annotate:
        annotate(run_path, bench_dir, rows, preds)
    a = table[-1]
    return {"detail": f"{minfo['kind']} {minfo.get('model_id') or Path(minfo.get('weights', '')).name}",
            "headline": f"BA {f(a['balanced_accuracy'])} | F {a['tp_F']}/{a['n_F']} "
                        f"| PF {a['tp_PF']}/{a['n_PF']}"}
