# Classification FT_D (val)

- model: yolo `last.pt` sha256 1b8877742a2b
- input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- preprocessing config: {'CLASSIFY_IMGSZ': '224', 'GREEN_CAST_G_GAIN': '1.24', 'MASK_BACKGROUND_IN_CROP': 'True', 'PAD_MODE': "'black'"}
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 558baf2c1af0, config.py ab2a90e64274
- git: 6532b51ea4 (dirty), created 2026-09-26 16:06:14 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.768 | 39/61 = 0.639 / 0.929 | 26/29 = 0.897 / 0.542 |
| blur | 90 | 0.609 | 49/61 = 0.803 / 0.742 | 12/29 = 0.414 / 0.500 |
| lowl | 90 | 0.496 | 50/61 = 0.820 / 0.676 | 5/29 = 0.172 / 0.312 |
| overx | 88 | 0.624 | 35/59 = 0.593 / 0.778 | 19/29 = 0.655 / 0.442 |
| rotate | 90 | 0.632 | 54/62 = 0.871 / 0.761 | 11/28 = 0.393 / 0.579 |
| warm | 90 | 0.598 | 31/63 = 0.492 / 0.795 | 19/27 = 0.704 / 0.373 |
| ALL | 538 | 0.621 | 258/367 = 0.703 / 0.766 | 92/171 = 0.538 / 0.458 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 258 | 109 |
| PF | 79 | 92 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 5.0 ms, p50 5.0 ms, p95 5.0 ms (batched crop prep + predict divided by number of beans; model load excluded)
- device: cpu
- cost: $0.0000 (API cost 0 (runs locally). Hardware and energy cost not measured.)

## Versus FT_C (same beans)

| variant | fixed | broken | net fixed |
|---|---|---|---|
| canon | 8 | 10 | -2 |
| blur | 27 | 16 | 11 |
| lowl | 6 | 11 | -5 |
| overx | 26 | 5 | 21 |
| rotate | 26 | 13 | 13 |
| warm | 16 | 9 | 7 |
| ALL | 109 | 64 | 45 |
