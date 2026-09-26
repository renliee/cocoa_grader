# eval/

KakaoLens test suite. One entry point, two tasks, every run saved under its own id.

For the baseline and current validation runs, see `results/README.md`.
Use `python -m eval.run` for all new runs.

## Layout

```
eval/
  run.py            CLI: python -m eval.run --task seg|cls ...
  seg.py            segmentation task: detected vs expected beans per photo
  cls.py            classification task: labels join, metrics, report
  models.py         model backends: local YOLO, OpenAI, Gemini, local OpenAI-compatible (Ollama)
  extract.py        builds a frozen crop benchmark once (python -m eval.extract --bench <id>)
  pipeline.py       calls backend/core exactly like the app does
  settings.py       paths, model aliases, prices, decision rules
  benchmarks/<id>/  committed manifests of each benchmark (crops themselves stay in data/bench/)
  results/
    segmentation/<run>/    run_config.json, per_photo.csv, per_variant.csv, report.md, annotated/, code_snapshot/
    classification/<run>/  run_config.json, predictions.csv, failures.csv,
                           report.md, annotated/, code_snapshot/
    B0_csv_full/, S0/      Phase I baseline results retained in their original locations
    index.csv              Runs made by this runner
```

## Rules the runner enforces

- Classification scores every model on the same frozen crops (`--bench`, default `S0_csv_full`) and the same
  label CSV. Crop idx N is paired with CSV idx N of the same photo. No matching to canon, no relabelling.
- A photo whose crop count differs from its label rows is listed as not scored, never guessed.
- API failures and unparseable answers stay in the denominator as `error` / `invalid` and count as wrong.
- Runs are never overwritten. `--split test` needs `--final` and is not used to choose settings.
- Every run writes `predictions.csv`, `failures.csv`, `report.md`, `run_config.json`, and `code_snapshot/`.
  Segmentation also writes `summary.csv`, `per_photo.csv`, and `per_variant.csv`.
  Classification keeps its per-variant metrics and confusion counts in `report.md` and `run_config.json`.
  The CLI is quiet on successful runs. A failed run retains an `INCOMPLETE` file with diagnostics.
- Each run copies the backend code it used into `code_snapshot/` with sha256 in `run_config.json`:
  seg runs keep `segment.py` + `config.py`; cls runs keep `segment.py` + `classify.py` + `config.py`.
  Crops always come from the benchmark, so for cls the note says whether `segment.py` still matches the
  file that cut them.
- YOLO classification calls `classify.prepare_crop` and `classify.classify_beans` and reads `config.py` live.
  Changes to crop preprocessing, batch settings, and the production prediction loop therefore affect new runs.

## Commands

```
python -m eval.run --task seg --split val --run S1
python -m eval.run --task cls --split val --model before --run B0_r
python -m eval.run --task cls --split val --model /actual/path/to/fine_tuned.pt --run FT1 --compare audit_before_val_20260926
python -m eval.run --task cls --split val --model gpt6_sol --limit 20 --run OAI_smoke1
python -m eval.run --task cls --split val --model gemini35_flash_lite --limit 20 --run GEM_smoke1
python -m eval.run --task cls --split val --model qwen3_vl_4b_instruct --limit 20 --workers 1 --run LOC_smoke1
python -m eval.run --task cls --split test --final --model before --run FINAL_before
```

The API/local aliases above resolve to exact IDs `gpt-6-sol`, `gemini-3.5-flash-lite`, and
`qwen3-vl:4b-instruct`. Any exact ID can also be selected with `openai:<id>`, `gemini:<id>`,
or `local:<id>`. The local alias needs a running Ollama endpoint with that model installed;
API keys alone do not provide it. Fine-tuned KakaoLens weights need only their real `.pt` path
and the same two class names; no alias or code edit is needed. Each successful run writes its
own `eval/results/classification/<run>/report.md`, `predictions.csv`, `failures.csv`, and
`run_config.json`.

`--limit N` makes a marked partial run for smoke tests. API keys come from the environment or
`eval/.env` (`OPENAI_API_KEY`, `GEMINI_API_KEY`). The local file is ignored by Git; copy
`eval/.env.example` or fill the prepared `eval/.env` with your own keys. Never put keys in CLI arguments,
run IDs, or chat messages. Model IDs are selected by exact-ID prefixes or the aliases above; token prices are only reported when
configured in `settings.PRICES` or passed through `--price-in` and `--price-out`.

## Development workflow

- To test a segmentation change, edit `backend/core/segment.py` or its `config.py` values, then run
  `--task seg --split val` with a new run ID. Compare `summary.csv` and `per_photo.csv` with
  `results/segmentation/audit_seg_val_20260926/`. The run snapshots both source files.
- To test classification preprocessing, edit `prepare_crop`, `classify_beans`, or their `config.py`
  values, then run `--task cls --split val --model before --compare audit_before_val_20260926`
  with a new run ID. The run reads the same frozen `S0_csv_full` crops and labels as the baseline.
  A change only to `segment.py` does not recut those crops; use a new benchmark ID if recutting is intended.
- To test fine-tuned weights, pass the actual `.pt` path to `--model` and use the same `--bench`
  and `--compare` arguments. Check BA and the fixed/broken bean counts in `report.md`.
- For an API model, start with `--limit 20` on `val`. Inspect `predictions.csv`, `failures.csv`,
  latency, token usage, and configured cost before a full `val` run. Use `test` only after selecting
  the model and settings.

The repo ignores `data/`. A commit or tag of `eval/` includes the benchmark manifest, but a fresh
clone also needs the matching `data/labels.csv`, photos, and `data/bench/S0_csv_full` crop cache.
Keep that frozen cache unchanged for fair classification comparisons.
