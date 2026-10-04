"""The dashboard's own state: games added by hand, install manifests, launch prefs."""
from __future__ import annotations

import json
import threading

from . import paths

_LOCK = threading.RLock()
_EMPTY = {"manual_games": [], "manifests": {}, "prefs": {}}


def _file():
    return paths.data_dir() / "state.json"


def load() -> dict:
    with _LOCK:
        try:
            d = json.loads(_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        for k, v in _EMPTY.items():
            d.setdefault(k, type(v)())
        return d


def save(state: dict) -> None:
    with _LOCK:
        tmp = _file().with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_file())


def update(fn):
    """Run fn(state) under the lock and save; returns fn's result."""
    with _LOCK:
        s = load()
        out = fn(s)
        save(s)
        return out
