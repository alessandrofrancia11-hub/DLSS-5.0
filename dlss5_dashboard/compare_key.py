"""An in-game hotkey that switches DLSS 5 on and off instantly, for A/B comparison.

It is a ReShade technique shortcut on the feeder's techniques (DLSS5_Feed and the
motion-vector pass before it), stored in the preset as
    Key<technique>@<file>.fx=<vk>,<ctrl>,<shift>,<alt>
With them off the add-on gets no DLSS evaluate, so the frame is the game's own:
no DLAA, no neural pass, and no cost.
"""
from __future__ import annotations

from pathlib import Path

from .inifile import IniDoc

KEYS = {"0,0,0,0": "Nessuno", "145,0,0,0": "Bloc Scorr (Scroll Lock)", "19,0,0,0": "Pausa",
        "120,0,1,0": "Shift + F9", "119,0,1,0": "Shift + F8", "35,0,0,0": "Fine (End)",
        "34,0,0,0": "Pag giu'"}
_MATCH = ("dlss5_feed", "lumenite")


def _preset(exe_dir: Path) -> Path | None:
    ini = exe_dir / "ReShade.ini"
    if not ini.exists():
        return None
    rel = IniDoc.load(ini).get("GENERAL", "PresetPath") or "ReShadePreset.ini"
    p = Path(rel.replace("\\", "/"))  # ReShade writes .\ReShadePreset.ini
    return p if p.is_absolute() else (exe_dir / p).resolve()


def techniques(preset: Path) -> list[str]:
    raw = IniDoc.load(preset).get(None, "Techniques") or ""
    return [t.strip() for t in raw.split(",")
            if t.strip() and any(m in t.lower() for m in _MATCH)]


def read(exe_dir: str | Path) -> dict | None:
    preset = _preset(Path(exe_dir))
    if not preset or not preset.exists():
        return None
    techs = techniques(preset)
    if not techs:
        return None
    doc = IniDoc.load(preset)
    return {"value": doc.get(None, f"Key{techs[-1]}") or "0,0,0,0", "techniques": techs,
            "options": KEYS}


def write(exe_dir: str | Path, key: str) -> list[str]:
    if key not in KEYS:
        raise ValueError("Tasto non valido.")
    preset = _preset(Path(exe_dir))
    if not preset or not preset.exists():
        raise ValueError("ReShadePreset.ini non trovato: installa prima il Feeder.")
    techs = techniques(preset)
    if not techs:
        raise ValueError("Tecniche DLSS5_Feed non trovate nel preset ReShade.")
    doc = IniDoc.load(preset)
    for t in techs:
        doc.set(None, f"Key{t}", key)
    doc.save(preset)
    return techs
