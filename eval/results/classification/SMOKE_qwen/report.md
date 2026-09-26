# Classification SMOKE_qwen (val)

- model: local `qwen3-vl:4b-instruct`
- input: raw crop from the benchmark, background set to black with the segmenter mask, no colour gain, lossless PNG, native crop size (median 164x257 px)
- prompt: v1
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 5f9d8a83f36c, config.py 20ebcca487d5
- git: e6482c29f0 (dirty), created 2026-09-26 17:48:57 WIB
- PARTIAL RUN: first 20 beans only, not comparable to full runs

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| blur | 20 | 0.500 | 15/15 = 1.000 / 0.750 | 0/5 = 0.000 / - |
| ALL | 20 | 0.500 | 15/15 = 1.000 / 0.750 | 0/5 = 0.000 / - |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 15 | 0 |
| PF | 5 | 0 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 3561.6 ms, p50 3342.4 ms, p95 6596.9 ms (wall time of all HTTP attempts and retry waits per bean; calls run in parallel, so per-bean latency is not throughput)
- tokens: 3151 in, 340 out
- cost: $0.0000 (API cost 0 (local endpoint); local GPU time is in latency, hardware and energy cost not measured)
