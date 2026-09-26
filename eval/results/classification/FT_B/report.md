# Classification FT_B (val)

- model: yolo `last.pt` sha256 06801283e8fa
- input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- preprocessing config: {'CLASSIFY_IMGSZ': '224', 'GREEN_CAST_G_GAIN': '1.24', 'MASK_BACKGROUND_IN_CROP': 'True', 'PAD_MODE': "'black'"}
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 558baf2c1af0, config.py ab2a90e64274
- git: a358243468 (dirty), created 2026-09-26 14:58:34 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.738 | 48/61 = 0.787 / 0.842 | 20/29 = 0.690 / 0.606 |
| blur | 90 | 0.504 | 51/61 = 0.836 / 0.680 | 5/29 = 0.172 / 0.333 |
| lowl | 90 | 0.547 | 52/61 = 0.852 / 0.703 | 7/29 = 0.241 / 0.438 |
| overx | 88 | 0.495 | 36/59 = 0.610 / 0.667 | 11/29 = 0.379 / 0.324 |
| rotate | 90 | 0.626 | 40/62 = 0.645 / 0.784 | 17/28 = 0.607 / 0.436 |
| warm | 90 | 0.624 | 32/63 = 0.508 / 0.821 | 20/27 = 0.741 / 0.392 |
| ALL | 538 | 0.587 | 259/367 = 0.706 / 0.740 | 80/171 = 0.468 / 0.426 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 259 | 108 |
| PF | 91 | 80 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 4.5 ms, p50 4.5 ms, p95 4.5 ms (batched crop prep + predict divided by number of beans; model load excluded)
- device: cpu
- cost: $0.0000 (API cost 0 (runs locally). Hardware and energy cost not measured.)

## Versus audit_before_val_20260926 (same beans)

| variant | fixed | broken | net fixed |
|---|---|---|---|
| canon | 42 | 9 | 33 |
| blur | 24 | 14 | 10 |
| lowl | 38 | 19 | 19 |
| overx | 24 | 9 | 15 |
| rotate | 39 | 11 | 28 |
| warm | 31 | 7 | 24 |
| ALL | 198 | 69 | 129 |

Verdict: BETTER (net 129 beans, rule >= 3)
