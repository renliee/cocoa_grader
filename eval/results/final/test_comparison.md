# Final test-set comparison

- Split: test
- Benchmark: S0_csv_full (manifest SHA256 a350a8cd8293a60cd23230ac574399637f77226465f6c7b1c6db4ebf266fe847)
- Labels SHA256: 753c4b4bca564168110a64ca0013fedf942e3b5c002dd3fa2e51b01f16c7936d
- Same beans scored: 525

## Performance

| Model | Beans | Accuracy | BA all | BA canon | BA blur | BA lowl | BA overx | BA rotate | BA warm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| before | 525 | 0.377 | 0.494 | 0.516 | 0.491 | 0.479 | 0.483 | 0.521 | 0.456 |
| FT_E | 525 | 0.606 | 0.607 | 0.791 | 0.592 | 0.597 | 0.484 | 0.654 | 0.530 |
| openai | 525 | 0.596 | 0.478 | 0.475 | 0.456 | 0.502 | 0.469 | 0.467 | 0.502 |
| qwen | 525 | 0.669 | 0.506 | 0.509 | 0.521 | 0.484 | 0.509 | 0.500 | 0.517 |

## Class errors

| Model | F recall | F precision | PF recall | PF precision | PF as F | Invalid | Error | Invalid + error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| before | 0.148 | 0.650 | 0.839 | 0.328 | 28 | 0 | 0 | 0 |
| FT_E | 0.604 | 0.757 | 0.609 | 0.433 | 68 | 0 | 0 | 0 |
| openai | 0.829 | 0.657 | 0.126 | 0.268 | 152 | 0 | 0 | 0 |
| qwen | 0.989 | 0.671 | 0.023 | 0.500 | 170 | 0 | 0 | 0 |

## Model setup, time and cost

### before

- Alias: before
- Identity: `3165f4496810515ba930d4a5a52a4fed136b0dec5c5b3bad9dcfb5550d61febd`
- Input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- Preprocessing: `{"CLASSIFY_IMGSZ": "224", "GREEN_CAST_G_GAIN": "1.24", "MASK_BACKGROUND_IN_CROP": "True", "PAD_MODE": "'black'"}`
- Prompt version: not applicable
- PAPER_WB_ENABLED: False
- Latency per bean: mean 4.8 ms, p95 4.8 ms. batched crop prep + predict divided by number of beans; model load excluded
- Total wall time: 9.7 s
- API cost (USD): API cost 0, hardware cost not measured; per 1,000 beans (USD): API cost 0

### FT_E

- Alias: FT_E
- Identity: `963200b87a498bff272d7ceecb79d2db67f28a7cfdf44feddb61b2ca13508e29`
- Input: classify.prepare_crop(crop, mask=mask), the same call classify_tray makes
- Preprocessing: `{"CLASSIFY_IMGSZ": "224", "GREEN_CAST_G_GAIN": "1.24", "MASK_BACKGROUND_IN_CROP": "True", "PAD_MODE": "'black'"}`
- Prompt version: not applicable
- PAPER_WB_ENABLED: True
- Latency per bean: mean 6.3 ms, p95 6.3 ms. batched crop prep + predict divided by number of beans; model load excluded
- Total wall time: 10.4 s
- API cost (USD): API cost 0, hardware cost not measured; per 1,000 beans (USD): API cost 0

### openai

- Alias: gpt6_sol
- Identity: `gpt-6-sol`
- Input: raw crop from the benchmark, background set to black with the segmenter mask, no colour gain, lossless PNG, native crop size (median 161x228 px)
- Preprocessing: `{}`
- Prompt version: v1
- PAPER_WB_ENABLED: True
- Latency per bean: mean 2598.3 ms, p95 4331.7 ms. wall time of all HTTP attempts and retry waits per bean; calls run in parallel, so per-bean latency is not throughput
- Total wall time: 345.5 s
- API cost (USD): 0.665016; per 1,000 beans (USD): 1.266697

### qwen

- Alias: qwen3_vl_4b_instruct
- Identity: `qwen3-vl:4b-instruct`
- Input: raw crop from the benchmark, background set to black with the segmenter mask, no colour gain, lossless PNG, native crop size (median 161x228 px)
- Preprocessing: `{}`
- Prompt version: v1
- PAPER_WB_ENABLED: True
- Latency per bean: mean 3296.8 ms, p95 3806.9 ms. wall time of all HTTP attempts and retry waits per bean; one worker; per-bean latency includes HTTP overhead
- Total wall time: 1735.5 s
- API cost (USD): API cost 0, hardware cost not measured; per 1,000 beans (USD): API cost 0

## Notes

- Test was run once per model after all model and parameter choices were made on val; any whole-run retry is listed below.
- LLM prompts were not tuned on test; prompt version is listed per model.
- API latency depends on network and parallel workers, so it is not directly comparable to local batch latency.
- FT_E uses paper colour normalization (PAPER_WB_ENABLED = True); before does not.
- Classification per_variant.csv files were derived from each run's saved predictions.csv.
- API cost uses reported token counts and the prices configured in the run; failed calls without token usage cannot be priced.
