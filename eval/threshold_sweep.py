"""Read-only: sweep the fermented decision threshold on a finished val run's predictions.

Changes nothing. Picks the threshold with the best balanced accuracy over all val variants,
subject to the same limit on under-fermented beans passed as fermented.
"""
import argparse
import csv

from eval import settings


def score(rows: list[dict], t: float) -> dict:
    tp_f = n_f = tp_pf = n_pf = pf_as_f = 0
    for r in rows:
        pred_f = float(r["p_fermented"]) >= t
        if r["label"] == "fermented":
            n_f += 1
            tp_f += pred_f
        else:
            n_pf += 1
            tp_pf += not pred_f
            pf_as_f += pred_f
    return {"t": t, "f": f"{tp_f}/{n_f}", "pf": f"{tp_pf}/{n_pf}", "pf_as_f": pf_as_f,
            "ba": (tp_f / n_f + tp_pf / n_pf) / 2}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="classification run on val, e.g. FT_E")
    ap.add_argument("--max-pf-as-f", type=int, default=47)
    args = ap.parse_args()
    path = settings.RESULTS / "classification" / args.run / "predictions.csv"
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["label"] in ("fermented", "poorly_fermented")]
    if not rows or rows[0].get("p_fermented", "") == "":
        raise SystemExit("predictions.csv has no p_fermented (only local YOLO runs have it)")
    if rows[0]["set"] != "val":
        raise SystemExit("Sweep on val only; test is never used to choose settings")
    canon = [r for r in rows if r["variant"] == "canon"]
    print(f"{'t':>5} | {'ALL BA':>6} {'F':>8} {'PF':>8} {'PF as F':>7} | {'canon BA':>8} {'F':>6} {'PF':>6}")
    best = None
    for i in range(5, 96, 5):
        t = i / 100
        a, c = score(rows, t), score(canon, t)
        if a["pf_as_f"] <= args.max_pf_as_f and (best is None or a["ba"] > best["ba"]):
            best = a
        print(f"{t:>5.2f} | {a['ba']:>6.3f} {a['f']:>8} {a['pf']:>8} {a['pf_as_f']:>7} | {c['ba']:>8.3f} {c['f']:>6} {c['pf']:>6}")
    print(f"\nBest with PF-as-F <= {args.max_pf_as_f}: t = {best['t']:.2f}, BA {best['ba']:.3f}"
          if best else "\nNo threshold meets the PF-as-F limit")


if __name__ == "__main__":
    main()
