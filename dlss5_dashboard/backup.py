"""Backups, uninstall and the on/off switch for whatever was put into a game folder.

Before an install the folder next to the game's .exe is snapshotted and every
file an installer could overwrite is copied away. After the install the
snapshot is diffed, so restore knows exactly which files are new (delete them)
and which were changed (put the copy back).

The on/off switch renames the proxy DLLs the install added (dxgi.dll,
d3d11.dll, ...) to *.dlss5off: the game then starts vanilla, with nothing
injected, and renaming them back turns everything on again.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from . import paths

PROXY_NAMES = {"dxgi.dll", "d3d11.dll", "d3d12.dll", "d3d10.dll", "d3d9.dll", "d3d8.dll",
               "dinput8.dll", "winmm.dll", "version.dll", "wininet.dll", "winhttp.dll",
               "opengl32.dll", "dbghelp.dll", "ddraw.dll", "optiscaler.asi"}
BACKUP_EXT = {".dll", ".ini", ".cfg", ".asi", ".addon", ".addon32", ".addon64", ".json",
              ".txt", ".fx", ".fxh", ".toml", ".xml"}
OFF = ".dlss5off"
SNAPSHOT_LIMIT = 60000


def snapshot(root: Path) -> dict[str, list[int]]:
    snap, n = {}, 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            n += 1
            if n > SNAPSHOT_LIMIT:
                return snap
            p = Path(dirpath) / f
            try:
                st = p.stat()
            except OSError:
                continue
            snap[p.relative_to(root).as_posix()] = [st.st_size, st.st_mtime_ns]
    return snap


def begin(game_id: str, exe_dir: str, route: str) -> dict:
    """Snapshot + copy of overwritable top-level files. Returns the manifest to finish()."""
    root = Path(exe_dir)
    safe = game_id.replace(":", "_")
    bdir = paths.sub("backups") / safe / time.strftime("%Y%m%d-%H%M%S")
    bdir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in root.iterdir():
        if f.is_file() and f.suffix.lower() in BACKUP_EXT:
            shutil.copy2(f, bdir / f.name)
            saved.append(f.name)
    return {"route": route, "exe_dir": str(root), "backup_dir": str(bdir), "saved": saved,
            "before": snapshot(root), "started": time.time(), "added": [], "changed": []}


def finish(manifest: dict) -> dict:
    root = Path(manifest["exe_dir"])
    before, after = manifest["before"], snapshot(root)
    manifest["added"] = sorted(k for k in after if k not in before)
    manifest["changed"] = sorted(k for k in after if k in before and after[k] != before[k])
    manifest["removed"] = sorted(k for k in before if k not in after)
    manifest["finished"] = time.time()
    return manifest


def proxies(manifest: dict) -> list[str]:
    """Top-level DLLs the install added that the game loads by name."""
    return [a for a in manifest.get("added", []) if "/" not in a and a.lower() in PROXY_NAMES]


def set_enabled(manifest: dict, enabled: bool) -> list[str]:
    """Rename the install's proxy DLLs on/off. Returns what was renamed."""
    root, done = Path(manifest["exe_dir"]), []
    for name in proxies(manifest):
        on, off = root / name, root / (name + OFF)
        src, dst = (off, on) if enabled else (on, off)
        if src.exists() and not dst.exists():
            src.rename(dst)
            done.append(f"{src.name} -> {dst.name}")
    return done


def is_enabled(manifest: dict) -> bool | None:
    root, names = Path(manifest["exe_dir"]), proxies(manifest)
    if not names:
        return None
    return all((root / n).exists() for n in names)


def restore(manifest: dict) -> list[str]:
    """Undo an install: delete what it added, put back what it changed."""
    root, log = Path(manifest["exe_dir"]), []
    set_enabled(manifest, True)
    bdir = Path(manifest["backup_dir"])
    before_dirs = {str(Path(k).parent.as_posix()) for k in manifest["before"]}
    for rel in manifest.get("added", []):
        p = root / rel
        if p.exists():
            p.unlink()
            log.append(f"rimosso {rel}")
    for rel in manifest.get("changed", []) + manifest.get("removed", []):
        src = bdir / rel
        if "/" not in rel and src.exists():
            shutil.copy2(src, root / rel)
            log.append(f"ripristinato {rel}")
        else:
            log.append(f"ATTENZIONE: {rel} era stato modificato ma non c'e' un backup "
                       f"(su Steam: Proprieta' > File installati > Verifica integrita')")
    # Remove folders the install created, deepest first, only if now empty.
    created = {str(Path(r).parent.as_posix()) for r in manifest.get("added", [])} - before_dirs
    for d in sorted(created, key=lambda s: s.count("/"), reverse=True):
        for parent in [Path(d), *Path(d).parents]:
            if str(parent.as_posix()) in (".", "") or str(parent.as_posix()) in before_dirs:
                break
            try:
                (root / parent).rmdir()
            except OSError:
                break
    return log
