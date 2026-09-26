import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eval import settings

NAME_RE = re.compile(r"^(train|val|test)_([a-z]+)_(\d+)$")
IMG_EXT = {".jpg", ".jpeg", ".png"}
BINARY = ("fermented", "poorly_fermented")
LABELS = ("fermented", "poorly_fermented", "defect", "skip")
_EMPTY = {"", "#n/a", "n/a", "na", "none", "nan"}
WIB = timezone(timedelta(hours=7))


def now() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")


def parse_name(stem: str) -> tuple[str, str, str] | None:
    m = NAME_RE.match(stem)
    return (m.group(1), m.group(2), m.group(3)) if m else None


def list_images(folder: Path) -> dict[str, Path]:
    if not folder.is_dir():
        raise SystemExit(f"Image folder not found: {folder}")
    found: dict[str, Path] = {}
    for p in sorted(folder.rglob("*")):
        if p.suffix.lower() not in IMG_EXT or settings.BENCH_ROOT in p.parents:
            continue
        if p.stem in found:
            raise SystemExit(f"Two images share the stem '{p.stem}': {found[p.stem].name}, {p.name}")
        found[p.stem] = p
    return found


def read_csv(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0] if text else ""
    # Excel with Indonesian locale exports with ';'
    delim = ";" if header.count(";") > header.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    return [{k.strip().lower(): (v or "").strip() for k, v in row.items() if k} for row in reader]


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0].keys()) if rows else [])
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_label(value: str) -> str | None:
    s = value.strip().lower().replace("-", "_").replace(" ", "_")
    if s in _EMPTY:
        return None
    if s in LABELS:
        return s
    raise ValueError(value)


def to_int(value: str) -> int:
    return int(float(value))


def validate_labels(by_stem: dict[str, list[dict]]) -> None:
    errors = []
    for stem, rows in by_stem.items():
        rows.sort(key=lambda r: r["idx"])
        idxs = [r["idx"] for r in rows]
        if idxs != list(range(len(rows))):
            errors.append(f"{stem}: idx is not 0..{len(rows) - 1} without gaps or duplicates")
        seen = {}
        for r in rows:
            c = r["canon_idx"]
            if c is None:
                continue
            if r["variant"] == "canon" and c != r["idx"]:
                errors.append(f"{stem} idx {r['idx']}: canon photo but canon_idx={c}")
            if c in seen:
                errors.append(f"{stem}: canon_idx {c} used by idx {seen[c]} and idx {r['idx']}")
            seen[c] = r["idx"]
    if errors:
        raise SystemExit("Label CSV problems:\n  " + "\n  ".join(errors[:40]))


def load_labels(path: Path) -> dict[str, list[dict]]:
    if not path.is_file():
        raise SystemExit(f"Label CSV not found: {path}")
    raw = read_csv(path)
    need = {"filename", "set", "variant", "sheet", "idx", "label"}
    missing = need - set(raw[0].keys()) if raw else need
    has_canon = bool(raw) and "canon_idx" in raw[0]
    if missing:
        raise SystemExit(f"Label CSV is missing columns: {sorted(missing)}")

    by_stem: dict[str, list[dict]] = {}
    errors = []
    for n, r in enumerate(raw, start=2):
        stem = Path(r["filename"]).stem
        if not stem:
            continue
        parsed = parse_name(stem)
        meta = (r["set"].lower(), r["variant"].lower(), str(to_int(r["sheet"])))
        # Metadata columns are the source of truth; the filename is a cross-check.
        if parsed is None or (parsed[0], parsed[1], str(int(parsed[2]))) != meta:
            errors.append(f"line {n}: {r['filename']} does not match set/variant/sheet {meta}")
        if meta[1] not in settings.VARIANTS:
            errors.append(f"line {n}: unknown variant '{meta[1]}'")
        try:
            label = norm_label(r["label"])
        except ValueError:
            errors.append(f"line {n}: unknown label '{r['label']}'")
            continue
        canon_raw = r["canon_idx"].lower() if has_canon else ""
        if canon_raw == "skip" or label == "skip":
            canon_idx, label = None, "skip"
        elif not has_canon:
            # No mapping in the CSV: canon beans map to themselves, extract derives the rest.
            if label is None:
                errors.append(f"line {n}: {stem} idx {r['idx']} has no label")
                continue
            canon_idx = to_int(r["idx"]) if meta[1] == "canon" else None
        elif canon_raw == "":
            errors.append(f"line {n}: {stem} idx {r['idx']} has a blank canon_idx")
            continue
        else:
            canon_idx = to_int(canon_raw)
            if label is None:
                errors.append(f"line {n}: {stem} idx {r['idx']} has canon_idx {canon_idx} but no label")
                continue
        by_stem.setdefault(stem, []).append({
            "stem": stem, "set": meta[0], "variant": meta[1], "sheet": meta[2],
            "idx": to_int(r["idx"]), "canon_idx": canon_idx, "label": label,
        })
    if errors:
        raise SystemExit("Label CSV problems:\n  " + "\n  ".join(errors[:40]))
    validate_labels(by_stem)
    return by_stem


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_info() -> dict:
    def run(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=settings.REPO, capture_output=True,
                                  text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""
    return {"head": run("rev-parse", "HEAD"),
            "dirty": bool(run("status", "--porcelain", "--untracked-files=no"))}


def run_dir(task: str, run_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id) or run_id in (".", ".."):
        raise SystemExit("Run id must use letters, numbers, dots, hyphens or underscores")
    d = settings.RESULTS / task / run_id
    if d.exists():
        raise SystemExit(f"Run {task}/{run_id} already exists. Runs are never overwritten; pick a new --run.")
    d.mkdir(parents=True)
    return d


def snapshot(run: Path, names: list[str]) -> dict:
    """Copy backend/core files into the run so we always know which code produced it."""
    out = run / "code_snapshot"
    out.mkdir(exist_ok=True)
    info = {}
    for name in names:
        src = settings.CORE / name
        shutil.copy2(src, out / name)
        info[name] = {"sha256": sha256(src), "copy": f"code_snapshot/{name}"}
    return info


def append_index(row: dict) -> None:
    path = settings.RESULTS / "index.csv"
    fields = ["task", "run", "split", "created", "git_head", "dirty", "detail", "headline"]
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow(row)


def fmt(x: float | None, digits: int = 3) -> str:
    return "-" if x is None else f"{x:.{digits}f}"
