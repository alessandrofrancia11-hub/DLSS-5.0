"""Where the dashboard keeps its own files (state, backups, downloads)."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "DLSS5-Dashboard"


def data_dir() -> Path:
    """%APPDATA%\\DLSS5-Dashboard on Windows, ~/DLSS5-Dashboard elsewhere.

    DLSS5_DASHBOARD_HOME overrides it (used by the tests).
    """
    override = os.environ.get("DLSS5_DASHBOARD_HOME")
    if override:
        d = Path(override)
    else:
        base = os.environ.get("APPDATA") or str(Path.home())
        d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def sub(name: str) -> Path:
    d = data_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d
