"""Starts a game with DLSS 5 on or off."""
from __future__ import annotations

import os
import shlex
import subprocess
import urllib.parse
from pathlib import Path

from . import backup, store


def launch(game: dict, dlss_on: bool, args: str = "") -> list[str]:
    log = []
    manifest = store.load()["manifests"].get(game["id"])
    if manifest:
        renamed = backup.set_enabled(manifest, dlss_on)
        log += renamed or [f"DLSS 5 gia' {'attivo' if dlss_on else 'disattivato'}"]
    elif dlss_on:
        log.append("Nessuna installazione gestita: il gioco parte senza modifiche.")

    args = (args or "").strip()
    store.update(lambda s: s["prefs"].setdefault(game["id"], {}).update(args=args, dlss_on=dlss_on))

    if game.get("appid"):
        url = f"steam://run/{game['appid']}//{urllib.parse.quote(args)}/" if args \
            else f"steam://rungameid/{game['appid']}"
        log.append(f"Avvio tramite Steam: {url}")
        _open(url)
    else:
        exe = Path(game["exe"])
        log.append(f"Avvio {exe.name} {args}".strip())
        subprocess.Popen([str(exe), *shlex.split(args, posix=False)], cwd=str(exe.parent))
    return log


def open_folder(path: str) -> None:
    _open(path)


def _open(target: str) -> None:
    if os.name == "nt":
        os.startfile(target)  # noqa: S606 - local user action
    else:
        subprocess.Popen(["xdg-open", target])
