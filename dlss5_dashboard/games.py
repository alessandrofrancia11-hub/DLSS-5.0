"""Finds installed games (Steam + added by hand) and reads what each one needs."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from . import pe, store

# Games with known layouts and quirks. Everything else is detected generically.
KNOWN = {
    "227300": {
        "name": "Euro Truck Simulator 2",
        "exe": "bin/win_x64/eurotrucks2.exe",
        "api": "D3D11",
        # The engine loads its renderer at run time and the exe names vulkan-1.dll too, so the
        # feeder's auto-detection can pick Vulkan (machine-wide layer, no local dxgi.dll) while
        # the game actually renders with DirectX 11 - ReShade then never loads.
        "feeder_api": "D3D",
        "notes": [
            "ETS2 non ha DLSS nativo: l'unica strada e' DLSS5-Feeder (ReShade + motion vector "
            "stimati), che fornisce DLAA e, se la DLL neurale lo permette, il passaggio DLSS 5.",
            "Usa il renderer DirectX 11 (predefinito). Con -opengl il percorso cambia.",
            "Non usare l'iniezione con TruckersMP (multiplayer): avvia il gioco in single player.",
        ],
    },
    "270880": {
        "name": "American Truck Simulator",
        "exe": "bin/win_x64/amtrucks.exe",
        "api": "D3D11",
        "feeder_api": "D3D",
        "notes": [
            "Stesso motore di ETS2: niente DLSS nativo, strada DLSS5-Feeder.",
            "Non usare l'iniezione con TruckersMP (multiplayer).",
        ],
    },
}

NOT_GAMES = {"228980", "1070560", "1391110", "1493710", "1628350", "2180100"}  # redists, runtimes
SKIP_EXE = ("unins", "setup", "crash", "redist", "vc_redist", "dxsetup", "prereq", "report",
            "helper", "cefprocess", "easyanticheat", "beservice", "install", "updater")

DLSS_FILES = {
    "nvngx_dlss.dll": "DLSS Super Resolution",
    "nvngx_dlssg.dll": "DLSS Frame Generation",
    "nvngx_dlssd.dll": "DLSS Ray Reconstruction",
    "sl.interposer.dll": "NVIDIA Streamline",
}
ANTICHEAT = {
    "easyanticheat": "Easy Anti-Cheat",
    "battleye": "BattlEye",
    "eac": "Easy Anti-Cheat",
    "vanguard": "Riot Vanguard",
    "anticheat": "Anti-cheat",
    "ricochet": "Ricochet",
    "nprotect": "nProtect",
}
COMPONENTS = {
    "dlss5-feed.cfg": "feeder_cfg",
    "dlss5-feed.addon64": "feeder",
    "dlss5-feed.addon32": "feeder",
    "reshade.ini": "reshade",
    "optiscaler.ini": "optiscaler",
    "nvngx_dlssnr.dll": "dlssnr",
}
WALK_LIMIT = 40000


# ------------------------------------------------------------------ Steam

def steam_root() -> Path | None:
    if os.name == "nt":
        try:
            import winreg
            for hive, key, val in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                   (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam",
                                    "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        p = Path(winreg.QueryValueEx(k, val)[0])
                        if p.exists():
                            return p
                except OSError:
                    continue
        except ImportError:
            pass
        p = Path(r"C:\Program Files (x86)\Steam")
        return p if p.exists() else None
    for p in (Path.home() / ".steam/steam", Path.home() / ".local/share/Steam"):
        if p.exists():
            return p
    return None


def parse_library_folders(text: str) -> list[str]:
    return [m.replace("\\\\", "\\") for m in re.findall(r'"path"\s+"([^"]+)"', text)]


def parse_acf(text: str) -> dict:
    out = {}
    for key in ("appid", "name", "installdir"):
        m = re.search(rf'"{key}"\s+"([^"]*)"', text, re.IGNORECASE)
        if m:
            out[key] = m.group(1)
    return out


def steam_games(root: Path | None = None) -> list[dict]:
    root = root or steam_root()
    if not root:
        return []
    libs = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    try:
        libs += [Path(p) for p in parse_library_folders(vdf.read_text(encoding="utf-8", errors="replace"))]
    except OSError:
        pass
    seen, games = set(), []
    for lib in libs:
        apps = lib / "steamapps"
        try:
            manifests = sorted(apps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for acf in manifests:
            try:
                info = parse_acf(acf.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            appid = info.get("appid")
            if not appid or appid in seen or appid in NOT_GAMES or "installdir" not in info:
                continue
            seen.add(appid)
            install = apps / "common" / info["installdir"]
            if not install.exists():
                continue
            name = info.get("name", info["installdir"])
            if re.search(r"redistributable|proton|steam linux runtime|steamworks", name, re.I):
                continue
            games.append({"id": f"steam:{appid}", "source": "steam", "appid": appid,
                          "name": KNOWN.get(appid, {}).get("name", name),
                          "install_dir": str(install)})
    return games


# ------------------------------------------------------------------ games

def find_exe(install_dir: Path, appid: str | None = None) -> Path | None:
    known = KNOWN.get(appid or "")
    if known:
        p = install_dir / known["exe"]
        if p.exists():
            return p
    best, best_size, n = None, -1, 0
    for dirpath, dirnames, filenames in os.walk(install_dir):
        depth = len(Path(dirpath).relative_to(install_dir).parts)
        if depth >= 4:
            dirnames[:] = []
        for f in filenames:
            n += 1
            if n > WALK_LIMIT:
                return best
            low = f.lower()
            if not low.endswith(".exe") or any(s in low for s in SKIP_EXE):
                continue
            try:
                size = (Path(dirpath) / f).stat().st_size
            except OSError:
                continue
            if size > best_size:
                best, best_size = Path(dirpath) / f, size
    return best


def manual_id(exe: str) -> str:
    return "manual:" + hashlib.sha1(os.path.normcase(exe).encode()).hexdigest()[:12]


def all_games() -> list[dict]:
    state = store.load()
    games = steam_games()
    for g in state["manual_games"]:
        games.append({**g, "source": "manual"})
    for g in games:
        g["installed_route"] = (state["manifests"].get(g["id"]) or {}).get("route")
    return sorted(games, key=lambda g: g["name"].lower())


def get(game_id: str) -> dict | None:
    for g in all_games():
        if g["id"] == game_id:
            return g
    return None


def add_manual(exe: str, name: str | None = None) -> dict:
    p = Path(exe)
    if not p.is_file() or p.suffix.lower() != ".exe":
        raise ValueError(f"Non e' un file .exe esistente: {exe}")
    g = {"id": manual_id(str(p)), "name": name or p.stem, "exe": str(p),
         "install_dir": str(p.parent)}

    def add(s):
        s["manual_games"] = [x for x in s["manual_games"] if x["id"] != g["id"]] + [g]
    store.update(add)
    return g


def remove_manual(game_id: str) -> None:
    store.update(lambda s: s.__setitem__(
        "manual_games", [x for x in s["manual_games"] if x["id"] != game_id]))


def _scan_tree(root: Path, ignore: set[str] = frozenset()) -> tuple[dict, dict]:
    """DLSS files and anti-cheat under root; paths in ignore (ours) don't count."""
    dlss, ac, n = {}, {}, 0
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            for k, label in ANTICHEAT.items():
                if d.lower() == k or (len(k) > 3 and d.lower().startswith(k)):
                    ac[label] = str(Path(dirpath) / d)
        for f in filenames:
            n += 1
            if n > WALK_LIMIT:
                return dlss, ac
            low = f.lower()
            if low in DLSS_FILES and os.path.normcase(str(Path(dirpath) / f)) not in ignore:
                dlss.setdefault(DLSS_FILES[low], str(Path(dirpath) / f))
            if low.startswith(("easyanticheat", "beservice", "battleye")):
                ac.setdefault("Anti-cheat", str(Path(dirpath) / f))
    return dlss, ac


def analyze(game: dict) -> dict:
    """Everything the UI shows about one game."""
    install = Path(game["install_dir"])
    appid = game.get("appid")
    exe = Path(game["exe"]) if game.get("exe") else find_exe(install, appid)
    known = KNOWN.get(appid or "", {})
    out = {**game, "exe": str(exe) if exe else None, "notes": list(known.get("notes", [])),
           "warnings": [], "feeder_api": known.get("feeder_api", "Auto")}
    if not exe or not exe.exists():
        out["warnings"].append("Eseguibile del gioco non trovato: aggiungilo a mano.")
        out.update(arch=None, api=None, native_dlss={}, anticheat={}, components={},
                   exe_dir=None, recommended_route=None)
        return out
    info = pe.read_pe(exe)
    api = known.get("api") or pe.guess_api(info["imports"])
    manifest = store.load()["manifests"].get(game["id"]) or {}
    ours = {os.path.normcase(str(Path(manifest["exe_dir"]) / a)) for a in manifest.get("added", [])}
    native, ac = _scan_tree(install, ours)
    comps = {}
    for f in exe.parent.iterdir():
        kind = COMPONENTS.get(f.name.lower())
        if kind:
            comps[kind] = str(f)
        elif f.name.lower().endswith(".dlss5off"):
            comps.setdefault("disabled", []).append(f.name)
    out.update(exe_dir=str(exe.parent), arch=info["machine"], api=api,
               native_dlss=native, anticheat=ac, components=comps,
               recommended_route="optiscaler" if "DLSS Super Resolution" in native else "feeder")
    if ac:
        out["warnings"].append("Anti-cheat rilevato (" + ", ".join(ac) + "): iniettare DLL puo' "
                               "portare al BAN. Usalo solo offline/single player o non usarlo.")
    if info["machine"] == "x86":
        out["notes"].append("Gioco a 32 bit: il Feeder usa il processo helper a 64 bit.")
    return out
