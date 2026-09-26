# Classification FT_A (val)

- model: yolo `last.pt` sha256 3333b7dc6009
- input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- preprocessing config: {'CLASSIFY_IMGSZ': '224', 'GREEN_CAST_G_GAIN': '1.24', 'MASK_BACKGROUND_IN_CROP': 'True', 'PAD_MODE': "'black'"}
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 558baf2c1af0, config.py ab2a90e64274
- git: a358243468, created 2026-09-26 14:58:29 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.694 | 30/61 = 0.492 / 0.909 | 26/29 = 0.897 / 0.456 |
| blur | 90 | 0.598 | 54/61 = 0.885 / 0.730 | 9/29 = 0.310 / 0.562 |
| lowl | 90 | 0.509 | 60/61 = 0.984 / 0.682 | 1/29 = 0.034 / 0.500 |
| overx | 88 | 0.495 | 36/59 = 0.610 / 0.667 | 11/29 = 0.379 / 0.324 |
| rotate | 90 | 0.695 | 53/62 = 0.855 / 0.803 | 15/28 = 0.536 / 0.625 |
| warm | 90 | 0.646 | 23/63 = 0.365 / 0.920 | 25/27 = 0.926 / 0.385 |
| ALL | 538 | 0.603 | 256/367 = 0.698 / 0.753 | 87/171 = 0.509 / 0.439 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 256 | 111 |
| PF | 84 | 87 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 4.7 ms, p50 4.7 ms, p95 4.7 ms (batched crop prep + predict divided by number of beans; model load excluded)
- device: cpu
- cost: $0.0000 (API cost 0 (runs locally). Hardware and energy cost not measured.)

## Versus audit_before_val_20260926 (same beans)

| variant | fixed | broken | net fixed |
|---|---|---|---|
| canon | 26 | 5 | 21 |
| blur | 29 | 12 | 17 |
| lowl | 44 | 23 | 21 |
| overx | 26 | 11 | 15 |
| rotate | 51 | 12 | 39 |
| warm | 22 | 2 | 20 |
| ALL | 198 | 65 | 133 |

Verdict: BETTER (net 133 beans, rule >= 3)
