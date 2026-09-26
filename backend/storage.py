"""Private, server-named photo artifacts stored beside SQLite."""
import hashlib
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from db import DATA_DIR

_ID = re.compile(r'^[a-f0-9]{32}$')
ASSET_ROOT = DATA_DIR / 'assets'


def photo_key(owner_id, photo_id, filename):
    if not _ID.fullmatch(owner_id) or not _ID.fullmatch(photo_id) or '/' in filename or '\\' in filename:
        raise ValueError('Invalid internal asset identifier')
    return f'assets/{owner_id}/{photo_id}/{filename}'


def _path(key):
    root = ASSET_ROOT.resolve()
    path = (DATA_DIR.resolve() / key).resolve()
    if root not in path.parents or not key.startswith('assets/'):
        raise ValueError('Invalid asset path')
    return path


def write_asset(key, payload):
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    try:
        with temp.open('wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    return hashlib.sha256(payload).hexdigest()


def read_asset(key, sha256=None):
    payload = _path(key).read_bytes()
    if sha256 and hashlib.sha256(payload).hexdigest() != sha256:
        raise ValueError('Stored asset checksum differs from manifest')
    return payload


def delete_photo_assets(owner_id, photo_id):
    if not _ID.fullmatch(owner_id) or not _ID.fullmatch(photo_id):
        raise ValueError('Invalid internal asset identifier')
    root = ASSET_ROOT.resolve()
    target = (root / owner_id / photo_id).resolve()
    if root not in target.parents or target.parent != (root / owner_id).resolve():
        raise ValueError('Photo asset path escapes data directory')
    if target.exists():
        shutil.rmtree(target)
