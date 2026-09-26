# Classification SMOKE_gemini (val)

- model: gemini `gemini-3.5-flash-lite`
- input: raw crop from the benchmark, background set to black with the segmenter mask, no colour gain, lossless PNG, native crop size (median 164x257 px)
- prompt: v1
- benchmark: S0_csv_full (crops cut with segment.py sha256 9248dacdc0ff), labels sha256 753c4b4bca56
- label rule: crop idx N = CSV idx N of the same photo; no matching to canon, no relabelling
- code: segment.py 9248dacdc0ff, classify.py 5f9d8a83f36c, config.py 20ebcca487d5
- git: e6482c29f0 (dirty), created 2026-09-26 17:47:00 WIB
- PARTIAL RUN: first 20 beans only, not comparable to full runs

| variant | beans | BA | F recall / precision | PF recall / precision |
|---|---|---|---|---|
| blur | 20 | 0.367 | 11/15 = 0.733 / 0.733 | 0/5 = 0.000 / - |
| ALL | 20 | 0.367 | 11/15 = 0.733 / 0.733 | 0/5 = 0.000 / - |

## Confusion matrix (all variants; rows = label)

| label \ pred | F | PF |
|---|---|---|
| F | 11 | 0 |
| PF | 4 | 0 |

Prediksi yang gagal atau tak terbaca ada di `failures.csv` dan tetap dihitung salah.

## Latency and cost

- latency per bean: mean 3853.2 ms, p50 2819.7 ms, p95 7909.2 ms (wall time of all HTTP attempts and retry waits per bean; calls run in parallel, so per-bean latency is not throughput)
- tokens: 17168 in, 307 out
- cost: not reported (cost = tokens x configured price)
