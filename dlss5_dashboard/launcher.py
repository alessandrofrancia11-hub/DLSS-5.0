"""Starts a game with DLSS 5 on or off."""
from __future__ import annotations

import os
import shlex
import subprocess
import urllib.parse
from pathlib import Path

from . import backup, store
from .inifile import IniDoc


def launch(game: dict, dlss_on: bool, args: str = "", neural_on: bool | None = None) -> list[str]:
    log = []
    manifest = store.load()["manifests"].get(game["id"])
    if manifest and neural_on is not None and manifest.get("route") == "optiscaler":
        ini = Path(manifest["exe_dir"]) / "OptiScaler.ini"
        if ini.exists():
            doc = IniDoc.load(ini)
            doc.set("DlssNr", "Enabled", "true" if neural_on else "false")
            doc.save(ini)
            log.append(f"Neurale DLSS 5 {'acceso' if neural_on else 'spento'} (OptiScaler.ini)")
    if manifest:
        renamed = backup.set_enabled(manifest, dlss_on)
        log += renamed or [f"DLSS 5 gia' {'attivo' if dlss_on else 'disattivato'}"]
    elif dlss_on:
        log.append("Nessuna installazione gestita: il gioco parte senza modifiche.")

    args = (args or "").strip()
    pref = {"args": args}
    if manifest:  # without an install the switch is meaningless: don't remember "off"
        pref["dlss_on"] = dlss_on
    store.update(lambda s: s["prefs"].setdefault(game["id"], {}).update(pref))

    if game.get("source") == "xbox":
        from . import xbox
        target = xbox.launch_target(game)
        if not target:
            raise RuntimeError("Pacchetto Xbox non trovato in Windows: avvia il gioco dall'app Xbox "
                               "(DLSS 5 resta comunque attivo/disattivo come impostato qui).")
        log.append(f"Avvio tramite Xbox: {target}")
        _open(target)
    elif game.get("appid"):
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
