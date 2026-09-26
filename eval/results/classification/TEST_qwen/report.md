# Classification TEST_qwen (test)

- model: local `qwen3-vl:4b-instruct`
- input: raw crop from the benchmark, background set to black with the segmenter mask, no colour gain, lossless PNG, native crop size (median 161x228 px)
- prompt: v1
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 5f9d8a83f36c, config.py 201a43553809
- git: ad06e99dc4, created 2026-09-26 18:41:18 WIB

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| canon | 90 | 0.509 | 60/61 = 0.984 / 0.682 | 1/29 = 0.034 / 0.500 |
| blur | 75 | 0.521 | 51/51 = 1.000 / 0.689 | 1/24 = 0.042 / 1.000 |
| lowl | 90 | 0.484 | 59/61 = 0.967 / 0.670 | 0/29 = 0.000 / 0.000 |
| overx | 90 | 0.509 | 60/61 = 0.984 / 0.682 | 1/29 = 0.034 / 0.500 |
| rotate | 90 | 0.500 | 56/56 = 1.000 / 0.622 | 0/34 = 0.000 / - |
| warm | 90 | 0.517 | 61/61 = 1.000 / 0.685 | 1/29 = 0.034 / 1.000 |
| ALL | 525 | 0.506 | 347/351 = 0.989 / 0.671 | 4/174 = 0.023 / 0.500 |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 347 | 4 |
| PF | 170 | 4 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 3296.8 ms, p50 3228.5 ms, p95 3806.9 ms (wall time of all HTTP attempts and retry waits per bean; calls run in parallel, so per-bean latency is not throughput)
- tokens: 82204 in, 8977 out
- cost: $0.0000 (API cost 0 (local endpoint); local GPU time is in latency, hardware and energy cost not measured)
