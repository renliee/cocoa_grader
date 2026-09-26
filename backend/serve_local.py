"""Run the persistent API locally during supervised checkpoints.

Usage: .venv\\Scripts\\python backend/serve_local.py --without-cv
"""
import argparse
import os
from pathlib import Path

import uvicorn


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--without-cv', action='store_true', help='Run identity and draft APIs while CV dependencies are unavailable')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if args.without_cv:
        os.environ['KAKAO_SKIP_MODEL_LOAD'] = '1'
    else:
        os.environ.setdefault('KAKAO_WEIGHTS', str(Path(__file__).resolve().parent / 'weights' / 'best.pt'))
        settings_dir = Path(__file__).resolve().parent.parent / 'data' / 'ultralytics'
        settings_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault('YOLO_CONFIG_DIR', str(settings_dir))
    os.environ['KAKAO_ALLOW_HTTP_COOKIES'] = '1'  # Explicit local HTTP only.
    uvicorn.run('main:app', host='127.0.0.1', port=args.port, workers=1)
