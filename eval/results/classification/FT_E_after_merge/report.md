# Classification FT_E_after_merge (val)

- model: yolo `best.pt` sha256 963200b87a49
- input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- preprocessing config: {'CLASSIFY_IMGSZ': '224', 'GREEN_CAST_G_GAIN': '1.24', 'MASK_BACKGROUND_IN_CROP': 'True', 'PAD_MODE': "'black'"}
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py c68cc41a9e86, classify.py 5f9d8a83f36c, config.py 201a43553809
- git: 9709af24fc (dirty), created 2026-09-26 18:53:01 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.793 | 40/61 = 0.656 / 0.952 | 27/29 = 0.931 / 0.562 |
| blur | 90 | 0.612 | 20/61 = 0.328 / 0.870 | 26/29 = 0.897 / 0.388 |
| lowl | 90 | 0.615 | 54/61 = 0.885 / 0.740 | 10/29 = 0.345 / 0.588 |
| overx | 88 | 0.481 | 14/59 = 0.237 / 0.636 | 21/29 = 0.724 / 0.318 |
| rotate | 90 | 0.690 | 39/62 = 0.629 / 0.848 | 21/28 = 0.750 / 0.477 |
| warm | 90 | 0.611 | 28/63 = 0.444 / 0.824 | 21/27 = 0.778 / 0.375 |
| ALL | 538 | 0.634 | 195/367 = 0.531 / 0.812 | 126/171 = 0.737 / 0.423 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 195 | 172 |
| PF | 45 | 126 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 6.3 ms, p50 6.3 ms, p95 6.3 ms (batched crop prep + predict divided by number of beans; model load excluded)
- device: cpu
- cost: $0.0000 (API cost 0 (runs locally). Hardware and energy cost not measured.)

## Versus FT_E (same beans)

| variant | fixed | broken | net fixed |
|---|---|---|---|
| canon | 0 | 0 | 0 |
| blur | 0 | 0 | 0 |
| lowl | 0 | 0 | 0 |
| overx | 0 | 0 | 0 |
| rotate | 0 | 0 | 0 |
| warm | 0 | 0 | 0 |
| ALL | 0 | 0 | 0 |

Verdict: NOT BETTER (net 0 beans, rule >= 3)
