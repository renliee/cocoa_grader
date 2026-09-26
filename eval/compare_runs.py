"""Compare completed classification runs on the same frozen benchmark."""

import csv
import json
import re
import sys
from pathlib import Path

import settings


ROOT = Path(__file__).resolve().parent / "results"
FIELDS = ("variant", "beans", "accuracy", "balanced_accuracy", "f_recall", "f_precision",
          "pf_recall", "pf_precision", "pf_as_f", "invalid", "error")


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"Missing {path}")
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict], fields) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def score(rows: list[dict], variant: str) -> dict:
    n_f = sum(r["label"] == "fermented" for r in rows)
    n_pf = sum(r["label"] == "poorly_fermented" for r in rows)
    tp_f = sum(r["label"] == r["pred"] == "fermented" for r in rows)
    tp_pf = sum(r["label"] == r["pred"] == "poorly_fermented" for r in rows)
    pred_f = sum(r["pred"] == "fermented" for r in rows)
    pred_pf = sum(r["pred"] == "poorly_fermented" for r in rows)
    recall_f = tp_f / n_f if n_f else None
    recall_pf = tp_pf / n_pf if n_pf else None
    return {"variant": variant, "beans": len(rows), "accuracy": (tp_f + tp_pf) / len(rows),
            "balanced_accuracy": (recall_f + recall_pf) / 2 if n_f and n_pf else None,
            "f_recall": recall_f, "f_precision": tp_f / pred_f if pred_f else None,
            "pf_recall": recall_pf, "pf_precision": tp_pf / pred_pf if pred_pf else None,
            "pf_as_f": sum(r["label"] == "poorly_fermented" and r["pred"] == "fermented" for r in rows),
            "invalid": sum(r["status"] == "invalid" for r in rows),
            "error": sum(r["status"] == "error" for r in rows)}


def load_run(run_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise SystemExit(f"Invalid run id: {run_id}")
    path = ROOT / "classification" / run_id
    if (path / "INCOMPLETE").exists():
        raise SystemExit(f"{run_id} is incomplete; see its INCOMPLETE file")
    try:
        config = json.loads((path / "run_config.json").read_text(encoding="utf-8"))
        wall_s = float((path / "wall_time_seconds.txt").read_text().strip())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{run_id}: missing or invalid run config or wall time: {exc}") from exc
    predictions = read_csv(path / "predictions.csv")
    if not predictions or config["limit"] is not None:
        raise SystemExit(f"{run_id}: empty or partial run cannot be compared")
    beans = {}
    for row in predictions:
        key = (row["stem"], int(row["idx"]))
        if key in beans:
            raise SystemExit(f"{run_id}: duplicate bean {key}")
        beans[key] = (row["set"], row["variant"], row["sheet"], row["label"])
    variants = sorted({r["variant"] for r in predictions}, key=lambda v: (v != "canon", v))
    per_variant = path / "per_variant.csv"
    if not per_variant.exists():
        derived = [score([r for r in predictions if r["variant"] == v], v) for v in variants]
        derived.append(score(predictions, "ALL"))
        write_csv(per_variant, derived, FIELDS)
    read_variants = read_csv(per_variant)
    variant_rows = {r["variant"]: r for r in read_variants}
    if len(variant_rows) != len(read_variants) or set(variant_rows) != set(variants) | {"ALL"}:
        raise SystemExit(f"{run_id}: per_variant.csv has different variants from predictions.csv")
    for variant in [*variants, "ALL"]:
        rows = predictions if variant == "ALL" else [r for r in predictions if r["variant"] == variant]
        expected = score(rows, variant)
        actual = variant_rows[variant]
        for field in FIELDS[1:]:
            if actual[field] == "" and expected[field] is None:
                continue
            if actual[field] == "" or expected[field] is None or abs(float(actual[field]) - float(expected[field])) > 1e-8:
                raise SystemExit(f"{run_id}: per_variant.csv disagrees with predictions.csv for {variant} {field}")
    snapshot = (path / "code_snapshot" / "config.py").read_text(encoding="utf-8")
    match = re.search(r"^PAPER_WB_ENABLED\s*=\s*(True|False)\s*$", snapshot, re.M)
    paper_wb = match.group(1) if match else "not recorded"
    return {"id": run_id, "path": path, "config": config, "predictions": predictions,
            "beans": beans, "variants": variant_rows, "wall_s": wall_s, "paper_wb": paper_wb}


def fmt(value, digits: int = 3) -> str:
    return "not reported" if value in (None, "") else f"{float(value):.{digits}f}"


def model_alias(model: dict) -> str:
    for alias, spec in settings.MODEL_ALIASES.items():
        if spec["kind"] == model["kind"]:
            if spec["kind"] == "yolo" and model["weights_sha256"].startswith(spec["sha256_prefix"]):
                return alias
            if spec.get("model_id") and spec["model_id"] == model.get("model_id"):
                return alias
    return Path(model["weights"]).stem if model["kind"] == "yolo" else "not reported"


def main(run_ids: list[str]) -> None:
    if len(run_ids) < 2:
        raise SystemExit("Usage: python eval/compare_runs.py RUN_ID RUN_ID [RUN_ID ...]")
    runs = [load_run(run_id) for run_id in run_ids]
    first = runs[0]
    base = first["config"]
    names = ("split", "benchmark id", "manifest SHA256", "labels SHA256")
    expected = (base["split"], base["benchmark"]["id"], base["benchmark"]["manifest_sha256"],
                base["labels"]["sha256"])
    if expected[0] != "test":
        raise SystemExit(f"Expected test split, got {expected[0]}")
    for run in runs[1:]:
        cfg = run["config"]
        found = (cfg["split"], cfg["benchmark"]["id"], cfg["benchmark"]["manifest_sha256"],
                 cfg["labels"]["sha256"])
        for name, want, got in zip(names, expected, found):
            if got != want:
                raise SystemExit(f"{run['id']}: {name} differs from {first['id']}: {got} != {want}")
        if set(run["beans"]) != set(first["beans"]):
            missing = set(first["beans"]) - set(run["beans"])
            extra = set(run["beans"]) - set(first["beans"])
            raise SystemExit(f"{run['id']}: scored beans differ from {first['id']}; "
                             f"missing {len(missing)}, extra {len(extra)}")
        for bean, details in first["beans"].items():
            if run["beans"][bean] != details:
                raise SystemExit(f"{run['id']}: bean {bean} label or variant differs from {first['id']}")
    for run in runs:
        if run["id"].endswith("_retry") and not (run["path"] / "retry_reason.txt").is_file():
            raise SystemExit(f"{run['id']}: missing retry_reason.txt for a whole-run retry")

    variants = [v for v in first["variants"] if v != "ALL"]
    fields = ["run", "model", "model_alias", "model_id_or_weights_sha256", "input", "preprocessing", "prompt_version",
              "paper_wb_enabled", "beans", "accuracy", "balanced_accuracy_all", "balanced_accuracy_canon",
              *[f"balanced_accuracy_{v}" for v in variants if v != "canon"],
              "f_recall", "f_precision", "pf_recall", "pf_precision", "pf_as_f", "invalid", "error",
              "invalid_plus_error", "latency_mean_ms", "latency_p95_ms", "latency_note", "wall_time_seconds",
              "api_cost_usd", "api_cost_per_1000_beans_usd"]
    rows = []
    for run in runs:
        cfg, model = run["config"], run["config"]["model"]
        overall = run["variants"]["ALL"]
        kind = model["kind"]
        if kind in ("openai", "gemini"):
            price = model.get("price_usd_per_1m_tokens")
            if price is None:
                cost = per_1000 = "not reported"
            else:
                tokens_in = sum(int(r["input_tokens"]) for r in run["predictions"] if r["input_tokens"])
                tokens_out = sum(int(r["output_tokens"]) for r in run["predictions"] if r["output_tokens"])
                total = (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000
                cost, per_1000 = f"{total:.6f}", f"{total / len(run['predictions']) * 1000:.6f}"
        else:
            cost, per_1000 = "API cost 0, hardware cost not measured", "API cost 0"
        rows.append({"run": run["id"], "model": run["id"].removeprefix("TEST_"),
                     "model_alias": model_alias(model),
                     "model_id_or_weights_sha256": model.get("model_id") or model.get("weights_sha256", ""),
                     "input": model["input"], "preprocessing": json.dumps(model.get("preprocessing_config", {})),
                     "prompt_version": model.get("prompt_version", "not applicable"),
                     "paper_wb_enabled": run["paper_wb"], "beans": len(run["predictions"]),
                     "accuracy": overall["accuracy"], "balanced_accuracy_all": overall["balanced_accuracy"],
                     "balanced_accuracy_canon": run["variants"]["canon"]["balanced_accuracy"],
                     **{f"balanced_accuracy_{v}": run["variants"][v]["balanced_accuracy"]
                        for v in variants if v != "canon"},
                     "f_recall": overall["f_recall"], "f_precision": overall["f_precision"],
                     "pf_recall": overall["pf_recall"], "pf_precision": overall["pf_precision"],
                     "pf_as_f": overall["pf_as_f"], "invalid": overall["invalid"], "error": overall["error"],
                     "invalid_plus_error": int(overall["invalid"]) + int(overall["error"]),
                     "latency_mean_ms": cfg["summary"]["latency_ms_mean"],
                     "latency_p95_ms": cfg["summary"]["latency_ms_p95"],
                     "latency_note": model["latency_note"], "wall_time_seconds": run["wall_s"],
                     "api_cost_usd": cost, "api_cost_per_1000_beans_usd": per_1000})

    out = ROOT / "final"
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "test_comparison.csv", rows, fields)
    lines = ["# Final test-set comparison", "",
             f"- Split: {expected[0]}", f"- Benchmark: {expected[1]} (manifest SHA256 {expected[2]})",
             f"- Labels SHA256: {expected[3]}", f"- Same beans scored: {len(first['beans'])}", "",
             "## Performance", "",
             "| Model | Beans | Accuracy | BA all | BA canon | " + " | ".join(f"BA {v}" for v in variants if v != "canon") + " |",
             "|---|---:|---:|---:|---:|" + "---:|" * (len(variants) - 1)]
    for row in rows:
        lines.append("| " + " | ".join([row["model"], str(row["beans"]), fmt(row["accuracy"]),
                     fmt(row["balanced_accuracy_all"]), fmt(row["balanced_accuracy_canon"]),
                     *[fmt(row[f"balanced_accuracy_{v}"]) for v in variants if v != "canon"]]) + " |")
    lines += ["", "## Class errors", "",
              "| Model | F recall | F precision | PF recall | PF precision | PF as F | Invalid | Error | Invalid + error |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append("| " + " | ".join([row["model"], fmt(row["f_recall"]), fmt(row["f_precision"]),
                     fmt(row["pf_recall"]), fmt(row["pf_precision"]), str(row["pf_as_f"]),
                     str(row["invalid"]), str(row["error"]), str(row["invalid_plus_error"])]) + " |")
    lines += ["", "## Model setup, time and cost", ""]
    for row in rows:
        lines += [f"### {row['model']}", "",
                  f"- Alias: {row['model_alias']}",
                  f"- Identity: `{row['model_id_or_weights_sha256']}`",
                  f"- Input: {row['input']}", f"- Preprocessing: `{row['preprocessing']}`",
                  f"- Prompt version: {row['prompt_version']}",
                  f"- PAPER_WB_ENABLED: {row['paper_wb_enabled']}",
                  f"- Latency per bean: mean {fmt(row['latency_mean_ms'], 1)} ms, "
                  f"p95 {fmt(row['latency_p95_ms'], 1)} ms. {row['latency_note']}",
                  f"- Total wall time: {fmt(row['wall_time_seconds'], 1)} s",
                  f"- API cost: {row['api_cost_usd']}; per 1,000 beans: {row['api_cost_per_1000_beans_usd']}", ""]
    lines += ["## Notes", "",
              "- Test was run once per model after all model and parameter choices were made on val; any whole-run retry is listed below.",
              "- LLM prompts were not tuned on test; prompt version is listed per model.",
              "- API latency depends on network and parallel workers, so it is not directly comparable to local batch latency.",
              "- FT_E uses paper colour normalization (PAPER_WB_ENABLED = True); before does not.",
              "- Classification per_variant.csv files were derived from each run's saved predictions.csv.",
              "- API cost uses reported token counts and the prices configured in the run; failed calls without token usage cannot be priced."]
    for run in runs:
        if run["id"].endswith("_retry"):
            reason = (run["path"] / "retry_reason.txt").read_text().strip()
            lines.append(f"- {run['id']} retried after a whole-run crash: {reason}")
    (out / "test_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
