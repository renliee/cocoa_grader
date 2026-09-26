# Classification FT_C (val)

- model: yolo `last.pt` sha256 e348df5ab097
- input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- preprocessing config: {'CLASSIFY_IMGSZ': '224', 'GREEN_CAST_G_GAIN': '1.24', 'MASK_BACKGROUND_IN_CROP': 'True', 'PAD_MODE': "'black'"}
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 558baf2c1af0, config.py ab2a90e64274
- git: a358243468 (dirty), created 2026-09-26 15:11:51 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.802 | 39/61 = 0.639 / 0.975 | 28/29 = 0.966 / 0.560 |
| blur | 90 | 0.636 | 25/61 = 0.410 / 0.862 | 25/29 = 0.862 / 0.410 |
| lowl | 90 | 0.591 | 49/61 = 0.803 / 0.731 | 11/29 = 0.379 / 0.478 |
| overx | 88 | 0.446 | 14/59 = 0.237 / 0.583 | 19/29 = 0.655 / 0.297 |
| rotate | 90 | 0.635 | 30/62 = 0.484 / 0.833 | 22/28 = 0.786 / 0.407 |
| warm | 90 | 0.574 | 21/63 = 0.333 / 0.808 | 22/27 = 0.815 / 0.344 |
| ALL | 538 | 0.614 | 178/367 = 0.485 / 0.802 | 127/171 = 0.743 / 0.402 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 178 | 189 |
| PF | 44 | 127 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 4.7 ms, p50 4.7 ms, p95 4.7 ms (batched crop prep + predict divided by number of beans; model load excluded)
- device: cpu
- cost: $0.0000 (API cost 0 (runs locally). Hardware and energy cost not measured.)

## Versus audit_before_val_20260926 (same beans)

| variant | fixed | broken | net fixed |
|---|---|---|---|
| canon | 33 | 1 | 32 |
| blur | 30 | 26 | 4 |
| lowl | 35 | 15 | 20 |
| overx | 14 | 13 | 1 |
| rotate | 30 | 7 | 23 |
| warm | 20 | 5 | 15 |
| ALL | 162 | 67 | 95 |

Verdict: BETTER (net 95 beans, rule >= 3)
