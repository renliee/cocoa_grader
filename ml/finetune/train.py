"""Fine-tune the KakaoLens classifier from the MVP weights. Runs on Colab or locally.

Augmentation is set explicitly: fermentation is read from colour, so no hue shift, no RandAugment,
only mild brightness/saturation jitter, near-full crops and flips. Fixed epochs, we keep last.pt.
"""
import argparse
import hashlib
import json
from pathlib import Path

from ultralytics import YOLO

AUG = dict(auto_augment=None, erasing=0.0, hsv_h=0.0, hsv_s=0.1, hsv_v=0.2, scale=0.1, fliplr=0.5, flipud=0.5)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="folder with train/ and val/")
    ap.add_argument("--weights", required=True, help="start weights, e.g. best_before.pt")
    ap.add_argument("--project", required=True)
    ap.add_argument("--name", required=True, help="run id, e.g. FT_A")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--lr0", type=float, default=5e-4)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--freeze", type=int, default=0, help="0 = train all layers, 10 = train only the head")
    ap.add_argument("--device", default="0")
    args = ap.parse_args()

    weights = Path(args.weights)
    cfg = dict(data=args.data, epochs=args.epochs, imgsz=224, batch=args.batch, optimizer="AdamW", lr0=args.lr0,
               freeze=args.freeze or None, seed=0, deterministic=True, patience=args.epochs, device=args.device,
               project=args.project, name=args.name, exist_ok=False, workers=2, plots=True, **AUG)
    model = YOLO(str(weights))
    model.train(**cfg)
    save_dir = Path(model.trainer.save_dir)
    last = save_dir / "weights" / "last.pt"
    record = {"start_weights": weights.name, "start_sha256": sha256(weights), "train_args": cfg,
              "last_pt_sha256": sha256(last), "data_json": None}
    dj = Path(args.data) / "dataset.json"
    if dj.exists():
        record["data_json"] = json.loads(dj.read_text())
    (save_dir / "finetune_record.json").write_text(json.dumps(record, indent=2, default=str))
    print(f"\nlast.pt: {last}\nsha256: {record['last_pt_sha256']}")


if __name__ == "__main__":
    main()
