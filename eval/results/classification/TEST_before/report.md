# Classification TEST_before (test)

- model: yolo `best.pt` sha256 3165f4496810
- input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- preprocessing config: {'CLASSIFY_IMGSZ': '224', 'GREEN_CAST_G_GAIN': '1.24', 'MASK_BACKGROUND_IN_CROP': 'True', 'PAD_MODE': "'black'"}
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 5f9d8a83f36c, config.py 20ebcca487d5
- git: e6482c29f0 (dirty), created 2026-09-26 18:04:06 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.516 | 4/61 = 0.066 / 0.800 | 28/29 = 0.966 / 0.329 |
| blur | 75 | 0.491 | 14/51 = 0.275 / 0.667 | 17/24 = 0.708 / 0.315 |
| lowl | 90 | 0.479 | 10/61 = 0.164 / 0.625 | 23/29 = 0.793 / 0.311 |
| overx | 90 | 0.483 | 19/61 = 0.311 / 0.655 | 19/29 = 0.655 / 0.311 |
| rotate | 90 | 0.521 | 4/56 = 0.071 / 0.800 | 33/34 = 0.971 / 0.388 |
| warm | 90 | 0.456 | 1/61 = 0.016 / 0.250 | 26/29 = 0.897 / 0.302 |
| ALL | 525 | 0.494 | 52/351 = 0.148 / 0.650 | 146/174 = 0.839 / 0.328 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 52 | 299 |
| PF | 28 | 146 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 4.8 ms, p50 4.8 ms, p95 4.8 ms (batched crop prep + predict divided by number of beans; model load excluded)
- device: cpu
- cost: $0.0000 (API cost 0 (runs locally). Hardware and energy cost not measured.)
