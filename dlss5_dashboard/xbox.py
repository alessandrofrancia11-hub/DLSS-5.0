"""Xbox app / PC Game Pass games.

Games installed by the Xbox app live in a folder per drive (C:\\XboxGames by
default; the drive's hidden .GamingRoot file names it). Each game has
<folder>\\<Game>\\Content\\MicrosoftGame.config with its package identity and
executables. Those Content folders are writable, so ReShade/OptiScaler work
there; games still in C:\\Program Files\\WindowsApps are locked and can't be
modified.

They must be started through Windows (shell:AppsFolder\\<PackageFamilyName>!<AppId>),
not by running the .exe: a Game Pass .exe started directly usually just exits.
"""
from __future__ import annotations

import os
import string
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

LAUNCHER_EXE = "gamelaunchhelper.exe"
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def parse_gaming_root(data: bytes) -> list[str]:
    """Paths listed in a .GamingRoot file ("RGBX", a count, UTF-16 strings)."""
    if data[:4] != b"RGBX":
        return []
    text = data[8:].decode("utf-16-le", errors="ignore")
    return [p.strip() for p in text.split("\0") if p.strip()]


def library_folders(drives: list[str] | None = None) -> list[Path]:
    """Every XboxGames folder on the given drive roots (all drives by default)."""
    if drives is None:
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")] \
            if os.name == "nt" else []
    found: list[Path] = []
    for root in drives:
        r = Path(root)
        candidates = []
        try:
            candidates = [r / p.lstrip("\\/") for p in parse_gaming_root((r / ".GamingRoot").read_bytes())]
        except OSError:
            pass
        candidates.append(r / "XboxGames")
        for c in candidates:
            if c.is_dir() and c not in found:
                found.append(c)
    return found


def _strip_ns(root: ET.Element) -> None:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def parse_config(path: Path) -> dict | None:
    """Identity, display name and executables from MicrosoftGame.config."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    _strip_ns(root)
    ident = root.find("Identity")
    if ident is None or not ident.get("Name"):
        return None
    shell = root.find("ShellVisuals")
    display = shell.get("DefaultDisplayName") if shell is not None else None
    exes = [{"name": e.get("Name"), "id": e.get("Id")}
            for e in root.findall("ExecutableList/Executable") if e.get("Name")]
    return {"identity": ident.get("Name"), "display": display, "executables": exes}


def pick_exe(content: Path, cfg: dict) -> Path | None:
    """The real game .exe: the config's, skipping Microsoft's launcher wrapper."""
    for e in cfg["executables"]:
        p = content / e["name"]
        if p.name.lower() != LAUNCHER_EXE and p.exists():
            return p
    from .games import find_exe  # the generic "largest .exe" search
    return find_exe(content)


def scan(folder: Path) -> list[dict]:
    games = []
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return games
    for d in entries:
        content = d / "Content"
        cfg = parse_config(content / "MicrosoftGame.config")
        if not cfg or not cfg["executables"]:
            continue  # DLC / add-on packages ship a config without executables
        name = cfg["display"]
        if not name or name.startswith("ms-resource:"):
            name = d.name
        app_id = next((e["id"] for e in cfg["executables"] if e["id"]), "Game")
        exe = pick_exe(content, cfg)
        games.append({"id": f"xbox:{cfg['identity']}", "source": "xbox", "name": name,
                      "install_dir": str(content), "exe": str(exe) if exe else None,
                      "xbox": {"identity": cfg["identity"], "app_id": app_id}})
    return games


def xbox_games(drives: list[str] | None = None) -> list[dict]:
    seen, out = set(), []
    for folder in library_folders(drives):
        for g in scan(folder):
            if g["id"] not in seen:
                seen.add(g["id"])
                out.append(g)
    return out


def family_name(identity: str) -> str | None:
    """PackageFamilyName (Name_publisherhash) of an installed package, via PowerShell."""
    if os.name != "nt":
        return None
    safe = identity.replace("'", "''")
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"(Get-AppxPackage -Name '{safe}' | Select-Object -First 1).PackageFamilyName"],
                           capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    out = p.stdout.strip()
    return out or None


def launch_target(game: dict) -> str | None:
    """shell:AppsFolder URI that starts the game the way the Xbox app does."""
    x = game.get("xbox") or {}
    pfn = family_name(x.get("identity", ""))
    if not pfn:
        return None
    return f"shell:AppsFolder\\{pfn}!{x.get('app_id') or 'Game'}"
