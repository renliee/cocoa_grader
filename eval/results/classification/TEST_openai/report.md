# Classification TEST_openai (test)

- model: openai `gpt-6-sol`
- input: raw crop from the benchmark, background set to black with the segmenter mask, no colour gain, lossless PNG, native crop size (median 161x228 px)
- prompt: v1
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 5f9d8a83f36c, config.py 201a43553809
- git: e6482c29f0 (dirty), created 2026-09-26 18:11:39 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.475 | 58/61 = 0.951 / 0.667 | 0/29 = 0.000 / 0.000 |
| blur | 75 | 0.456 | 38/51 = 0.745 / 0.655 | 4/24 = 0.167 / 0.235 |
| lowl | 90 | 0.502 | 57/61 = 0.934 / 0.679 | 2/29 = 0.069 / 0.333 |
| overx | 90 | 0.469 | 32/61 = 0.525 / 0.653 | 12/29 = 0.414 / 0.293 |
| rotate | 90 | 0.467 | 49/56 = 0.875 / 0.605 | 2/34 = 0.059 / 0.222 |
| warm | 90 | 0.502 | 57/61 = 0.934 / 0.679 | 2/29 = 0.069 / 0.333 |
| ALL | 525 | 0.478 | 291/351 = 0.829 / 0.657 | 22/174 = 0.126 / 0.268 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 291 | 60 |
| PF | 152 | 22 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 2598.3 ms, p50 2264.2 ms, p95 4331.7 ms (wall time of all HTTP attempts and retry waits per bean; calls run in parallel, so per-bean latency is not throughput)
- tokens: 64293 in, 53643 out
- cost: $0.6650 (cost = tokens x configured price)
