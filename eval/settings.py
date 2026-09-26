from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
CORE = BACKEND / "core"

# Photos live in subfolders under data/ (data/val/blur/val_blur_1.jpeg, data/train/...).
IMAGES_DIR = REPO / "data"
LABELS_CSV = REPO / "data" / "labels.csv"

# Optional per-photo override: filename,gt_count. Missing file means every photo has GT_COUNT beans.
GT_COUNTS_CSV = REPO / "data" / "gt_counts.csv"
GT_COUNT = 15

# Frozen crops (built once by eval.extract). Every classification run reads this, so all models
# see the same beans. Crops stay in data/ (untracked); small manifests go to eval/benchmarks/.
BENCH_ROOT = REPO / "data" / "bench"
TRACKED_BENCH = REPO / "eval" / "benchmarks"
DEFAULT_BENCH = "S0_csv_full"

RESULTS = REPO / "eval" / "results"

SETS = ("train", "val", "test")
VARIANTS = ("canon", "blur", "lowl", "overx", "rotate", "warm")

# Labels were made with these versions. Contour order (idx) can change if they differ.
EXPECTED_CV2 = "5.0.0"
EXPECTED_NUMPY = "2.4.4"

# --model aliases. sha256_prefix guards against the file being replaced by a fine-tuned one.
MODEL_ALIASES = {
    "before": {"kind": "yolo", "weights": BACKEND / "weights" / "best.pt", "sha256_prefix": "3165f4496810"},
    "gpt6_sol": {"kind": "openai", "model_id": "gpt-6-sol"},
    "gemini35_flash_lite": {"kind": "gemini", "model_id": "gemini-3.5-flash-lite"},
    "qwen3_vl_4b_instruct": {"kind": "local", "model_id": "qwen3-vl:4b-instruct"},
}

OPENAI_BASE_URL = "https://api.openai.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
LOCAL_BASE_URL = "http://localhost:11434/v1"   # Ollama's OpenAI-compatible endpoint

# USD per 1M tokens (input, output), keyed by the exact model ID. Copy from the provider's
# pricing page. A model missing here gets no cost figure, never a guessed one.
PRICES: dict[str, tuple[float, float]] = {}

# Decision rules, counted in beans. Fix these before comparing runs.
IMPROVE_NET_FIXED = 3    # a candidate beats its parent only if (fixed - broken) >= this on val
CONFIDENT_WRONG = 0.90   # wrong predictions at or above this confidence are listed

GATE_IMAGES = REPO / "ml" / "gate" / "images"
GATE_LABELS = REPO / "ml" / "gate" / "gate_labels.csv"
GATE_EXPECTED = {"fermented": (15, 21), "poorly_fermented": (84, 100)}
