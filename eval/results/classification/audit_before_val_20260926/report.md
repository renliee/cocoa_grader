# Classification audit_before_val_20260926 (val)

- model: yolo `best.pt` sha256 3165f4496810
- input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- preprocessing config: {'CLASSIFY_IMGSZ': '224', 'GREEN_CAST_G_GAIN': '1.24', 'MASK_BACKGROUND_IN_CROP': 'True', 'PAD_MODE': "'black'"}
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 558baf2c1af0, config.py ab2a90e64274
- git: ddcfe0a35f, created 2026-09-26 12:34:18 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.549 | 6/61 = 0.098 / 1.000 | 29/29 = 1.000 / 0.345 |
| blur | 90 | 0.504 | 32/61 = 0.525 / 0.681 | 14/29 = 0.483 / 0.326 |
| lowl | 90 | 0.536 | 17/61 = 0.279 / 0.739 | 23/29 = 0.793 / 0.343 |
| overx | 88 | 0.438 | 13/59 = 0.220 / 0.565 | 19/29 = 0.655 / 0.292 |
| rotate | 90 | 0.449 | 7/62 = 0.113 / 0.538 | 22/28 = 0.786 / 0.286 |
| warm | 90 | 0.508 | 1/63 = 0.016 / 1.000 | 27/27 = 1.000 / 0.303 |
| ALL | 538 | 0.495 | 76/367 = 0.207 / 0.673 | 134/171 = 0.784 / 0.315 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 76 | 291 |
| PF | 37 | 134 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 5.4 ms, p50 5.4 ms, p95 5.4 ms (batched crop prep + predict divided by number of beans; model load excluded)
- device: cpu
- cost: $0.0000 (API cost 0 (runs locally). Hardware and energy cost not measured.)
