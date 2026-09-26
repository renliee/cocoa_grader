"""KakaoLens test suite. One entry point for segmentation and classification runs.

  python -m eval.run --task seg --split val --run S0
  python -m eval.run --task cls --split val --model before --run B0
"""
import argparse
import io
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from eval import cls, common, pipeline, seg, settings

TASK_DIR = {"seg": "segmentation", "cls": "classification"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True, choices=["seg", "cls"])
    ap.add_argument("--split", required=True, choices=["val", "test"])
    ap.add_argument("--run", required=True, help="unique run id; existing runs are never overwritten")
    ap.add_argument("--model", help="cls: alias from settings.MODEL_ALIASES, path to .pt, openai:<id>, gemini:<id>, local:<id>")
    ap.add_argument("--final", action="store_true", help="required for --split test")
    ap.add_argument("--limit", type=int, help="smoke test on the first N beans/photos (marked partial)")
    ap.add_argument("--no-annotate", action="store_true")
    ap.add_argument("--allow-env-mismatch", action="store_true")
    g = ap.add_argument_group("seg")
    g.add_argument("--annotate-all", action="store_true", help="draw every photo, not only miscounted ones")
    g = ap.add_argument_group("cls")
    g.add_argument("--bench", default=settings.DEFAULT_BENCH)
    g.add_argument("--labels", type=Path, default=settings.LABELS_CSV)
    g.add_argument("--exclude", nargs="*", default=[], help="photo stems to leave out (reported in the run)")
    g.add_argument("--compare", help="earlier classification run id to compare bean by bean")
    g = ap.add_argument_group("cls, API models")
    g.add_argument("--prompt", default="v1")
    g.add_argument("--price-in", type=float, help="USD per 1M input tokens (overrides settings.PRICES)")
    g.add_argument("--price-out", type=float, help="USD per 1M output tokens")
    g.add_argument("--workers", type=int, default=4)
    g.add_argument("--timeout", type=float, default=60)
    g.add_argument("--endpoint", help="override base URL, e.g. http://localhost:11434/v1")
    g.add_argument("--unmasked", action="store_true", help="send the crop without blacking out the background")
    args = ap.parse_args()

    if args.split == "test" and not args.final:
        raise SystemExit("Test is for the final report only, never for choosing settings. Add --final if that is now.")
    if args.task == "cls" and not args.model:
        raise SystemExit("--task cls needs --model")
    run_path = common.run_dir(TASK_DIR[args.task], args.run)
    log = io.StringIO()
    exit_code = 0
    with redirect_stdout(log), redirect_stderr(log):
        try:
            pipeline.check_env(args.allow_env_mismatch)
            out = (seg if args.task == "seg" else cls).run(args, run_path)
            cfg = common.read_json(run_path / "run_config.json")
            common.append_index({"task": args.task, "run": args.run, "split": args.split, "created": cfg["created"],
                                 "git_head": cfg["git"]["head"][:10], "dirty": cfg["git"]["dirty"], **out})
        except BaseException as exc:
            # Keep partial artifacts for diagnosis; never delete a result.
            traceback.print_exception(exc)
            exit_code = 1
    output = log.getvalue()
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "LOCAL_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            output = output.replace(secret, "[REDACTED]")
    if exit_code:
        (run_path / "INCOMPLETE").write_text(output or "Runner stopped before completing this run.\n",
                                                encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
