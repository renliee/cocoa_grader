# Classification TEST_FT_E (test)

- model: yolo `FT_E.pt` sha256 963200b87a49
- input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- preprocessing config: {'CLASSIFY_IMGSZ': '224', 'GREEN_CAST_G_GAIN': '1.24', 'MASK_BACKGROUND_IN_CROP': 'True', 'PAD_MODE': "'black'"}
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 5f9d8a83f36c, config.py 201a43553809
- git: e6482c29f0 (dirty), created 2026-09-26 18:05:14 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.791 | 46/61 = 0.754 / 0.902 | 24/29 = 0.828 / 0.615 |
| blur | 75 | 0.592 | 20/51 = 0.392 / 0.800 | 19/24 = 0.792 / 0.380 |
| lowl | 90 | 0.597 | 56/61 = 0.918 / 0.727 | 8/29 = 0.276 / 0.615 |
| overx | 90 | 0.484 | 17/61 = 0.279 / 0.654 | 20/29 = 0.690 / 0.312 |
| rotate | 90 | 0.654 | 42/56 = 0.750 / 0.737 | 19/34 = 0.559 / 0.576 |
| warm | 90 | 0.530 | 31/61 = 0.508 / 0.705 | 16/29 = 0.552 / 0.348 |
| ALL | 525 | 0.607 | 212/351 = 0.604 / 0.757 | 106/174 = 0.609 / 0.433 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 212 | 139 |
| PF | 68 | 106 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 6.3 ms, p50 6.3 ms, p95 6.3 ms (batched crop prep + predict divided by number of beans; model load excluded)
- device: cpu
- cost: $0.0000 (API cost 0 (runs locally). Hardware and energy cost not measured.)
