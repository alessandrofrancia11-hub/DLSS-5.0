"""Every parameter the dashboard can change, the file it lives in, and its range.

Feeder keys are the ones dlss5-feed.cfg actually reads (verified against the
DLSS5-Feeder docs and DLSS5-Autopilot's feedcfg.py). OptiScaler keys come from
the OptiScaler.ini shipped by the DLSS-NR forks. "auto" means: leave it to the
tool's own default.
"""
from __future__ import annotations

from pathlib import Path

from .inifile import IniDoc

PRESET_LETTERS = {0: "Default", 1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H",
                  9: "I", 10: "J", 11: "K", 12: "L", 13: "M", 14: "N", 15: "O"}


def _f(section, key, label, type_, help_="", **kw):
    return {"section": section, "key": key, "label": label, "type": type_, "help": help_, **kw}


FEEDER = {
    "file": "dlss5-feed.cfg",
    "title": "DLSS5-Feeder (giochi senza DLSS nativo)",
    "groups": [
        {"title": "Generale", "fields": [
            _f(None, "enabled", "Feeder attivo", "select", "Spegne il Feeder senza disinstallare.",
               options={"1": "Acceso", "0": "Spento"}, default="1"),
            _f(None, "mode", "Modalita'", "select",
               "Full = DLAA + passaggio neurale. Transport test serve solo per diagnosi.",
               options={"2": "Full DLSS (normale)", "1": "Solo test trasporto", "0": "Off"},
               default="2"),
            _f(None, "preset", "Preset DLSS", "select",
               "Se vedi deformazioni su fiamme/trasparenze prova E o F (CNN).",
               options={"0": "Default (decide l'add-on)", "5": "E - CNN legacy",
                        "6": "F - CNN legacy", "10": "J - transformer",
                        "11": "K - transformer (piu' recente)"}, default="0"),
            _f(None, "work_resolution", "Risoluzione di lavoro neurale (%)", "number",
               "Area su cui gira il passaggio neurale. Piu' bassa = piu' FPS, meno dettaglio. "
               "Il Feeder e' sempre DLAA: Quality/Performance qui non esistono.",
               min=50, max=100, step=5, default="100"),
        ]},
        {"title": "Immagine", "fields": [
            _f(None, "hdr", "HDR", "select", "", options={"-1": "Auto", "0": "Forza SDR",
                                                           "1": "Forza HDR"}, default="-1"),
            _f(None, "depth_inverted", "Depth buffer", "select",
               "Cambia solo se l'effetto appare 'scollato' dalla scena.",
               options={"-1": "Segui ReShade", "0": "Forza non invertito", "1": "Forza invertito"},
               default="-1"),
        ]},
        {"title": "Avanzate (motion vector)", "advanced": True, "fields": [
            _f(None, "mv_scale_x", "Scala motion vector X", "number", "", min=-4, max=4, step=0.05,
               default="1.0"),
            _f(None, "mv_scale_y", "Scala motion vector Y", "number", "", min=-4, max=4, step=0.05,
               default="1.0"),
            _f(None, "create_delay", "Ritardo creazione (frame)", "number",
               "Frame da attendere prima di creare la sessione DLSS.", min=0, max=600, step=10,
               default="60"),
        ]},
    ],
}

_BOOL = {"auto": "Auto", "true": "Si'", "false": "No"}

OPTISCALER = {
    "file": "OptiScaler.ini",
    "title": "OptiScaler (giochi con DLSS nativo)",
    "groups": [
        {"title": "DLSS Super Resolution", "fields": [
            _f("DLSS", "RenderPresetOverride", "Forza preset", "select", "", options=_BOOL),
            _f("DLSS", "RenderPresetForAll", "Preset per tutte le qualita'", "select",
               "K = transformer di 2a generazione, consigliato su RTX 40.",
               options={"auto": "Auto", **{str(k): v for k, v in PRESET_LETTERS.items()}}),
            _f("QualityOverrides", "QualityRatioOverrideEnabled", "Rapporti di scala personalizzati",
               "select", "", options=_BOOL),
            _f("QualityOverrides", "QualityRatioQuality", "Rapporto Quality", "number",
               "1.5 = render a 1/1.5 della risoluzione", min=1.0, max=3.0, step=0.05, auto=True),
            _f("QualityOverrides", "QualityRatioBalanced", "Rapporto Balanced", "number", "",
               min=1.0, max=3.0, step=0.05, auto=True),
            _f("QualityOverrides", "QualityRatioPerformance", "Rapporto Performance", "number", "",
               min=1.0, max=3.0, step=0.05, auto=True),
            _f("OutputScaling", "Enabled", "Output scaling (supersampling)", "select",
               "Renderizza sopra la nativa e riscala: piu' nitido, piu' pesante.", options=_BOOL),
            _f("OutputScaling", "Multiplier", "Moltiplicatore output", "number", "",
               min=0.5, max=3.0, step=0.1, auto=True),
        ]},
        {"title": "Nitidezza", "fields": [
            _f("Sharpness", "OverrideSharpness", "Forza nitidezza", "select", "", options=_BOOL),
            _f("Sharpness", "Shader", "Shader", "select", "",
               options={"auto": "Auto (RCAS)", "rcas": "RCAS", "da": "Depth-adaptive",
                        "lcda": "Local contrast DA"}),
            _f("Sharpness", "Sharpness", "Intensita'", "number", "", min=0, max=1.3, step=0.05,
               auto=True),
        ]},
        {"title": "DLSS 5 Neural Rendering", "fields": [
            _f("DlssNr", "ToggleKey", "Tasto Neural Rendering on/off (in gioco)", "select",
               "Accende/spegne all'istante SOLO il passaggio neurale, per confrontare.",
               options={"auto": "Nessuno", "145": "Bloc Scorr (Scroll Lock)", "19": "Pausa",
                        "120": "F9", "121": "F10", "35": "Fine (End)"}),
            _f("DlssNr", "Enabled", "Neural Rendering", "select",
               "Serve nvngx_dlssnr.dll accanto al gioco. Su RTX 40 solo con build modificata.",
               options=_BOOL),
            _f("DlssNr", "TransferStrength", "Intensita' dettaglio", "number",
               "0 = bypass, 1 = immagine del modello, >1 esagera.", min=0, max=2, step=0.05,
               auto=True),
            _f("DlssNr", "ColourStrength", "Intensita' colore", "number",
               "0 = colori originali del gioco, 1 = colori del modello.", min=0, max=2, step=0.05,
               auto=True),
            _f("DlssNr", "Intensity", "Intensity (modello)", "number",
               "Parametro NVIDIA non documentato.", min=0, max=2, step=0.05, auto=True),
            _f("DlssNr", "WorkingScale", "Scala di lavoro", "number",
               "<1 = piu' veloce, >1 = supersampling (DX12/Vulkan).", min=0.25, max=2, step=0.05,
               auto=True),
            _f("DlssNr", "MaxRatio", "Protezione luci (max schiarimento)", "number", "",
               min=1, max=4, step=0.1, auto=True),
            _f("DlssNr", "Preset", "Preset modello", "number", "Richiede riavvio del gioco.",
               min=0, max=10, step=1, auto=True),
            _f("DlssNr", "Style", "Stile modello", "number", "Non documentato.", min=0, max=10,
               step=1, auto=True),
            _f("DlssNr", "DebugView", "Vista debug", "select", "",
               options={"auto": "Off", "1": "Input del modello", "2": "Output grezzo",
                        "3": "Differenza x20"}),
        ]},
        {"title": "Frame Generation multipla su RTX 40 (MFG unlock)", "fields": [
            _f("MfgUnlock", "Enabled", "Sblocco MFG 3x/4x", "select",
               "Solo build '-rtx40-mfg', solo giochi con DLSS-FG nativo, MAI in multiplayer.",
               options=_BOOL),
            _f("MfgUnlock", "ForceMultiplier", "Moltiplicatore forzato", "select", "",
               options={"auto": "Auto (dal menu del gioco)", "2": "2x", "3": "3x", "4": "4x",
                        "6": "6x"}),
            _f("MfgUnlock", "ForceFlipMeteringOff", "Fix immagine bloccata", "select",
               "Attivalo solo se a 3x/4x l'immagine si blocca.", options=_BOOL),
        ]},
        {"title": "Overlay e diagnostica", "fields": [
            _f("Menu", "OverlayMenu", "Tipo di menu", "select",
               "Se INSERT e i tasti (es. Bloc Scorr) non fanno nulla, metti 'Classico': il menu viene "
               "disegnato dentro il DLSS e i tasti tornano a funzionare. Disattiva la Frame Generation "
               "di OptiScaler (non quella del gioco).",
               options={"auto": "Auto (overlay)", "true": "Overlay", "false": "Classico (consigliato se i tasti non vanno)"}),
            _f("Menu", "ShortcutKey", "Tasto menu OptiScaler", "select", "Predefinito: INSERT.",
               options={"auto": "INSERT (predefinito)", "36": "Home", "35": "Fine (End)",
                        "121": "F10"}),
            _f("Log", "LogToFile", "Log su file (OptiScaler.log)", "select",
               "Serve a 'Verifica DLSS 5'. Spegnilo dopo: rallenta un po'.", options=_BOOL),
        ]},
        {"title": "Upscaler", "advanced": True, "fields": [
            _f("Upscalers", "Dx11Upscaler", "Upscaler DX11", "select",
               "dlss_12 e' l'unico che in DX11 permette anche il Neural Rendering.",
               options={"auto": "Auto", "dlss": "DLSS (DX11 nativo)", "dlss_12": "DLSS via DX12",
                        "fsr22": "FSR 2.2", "xess_12": "XeSS"}),
            _f("Upscalers", "Dx12Upscaler", "Upscaler DX12", "select", "",
               options={"auto": "Auto", "dlss": "DLSS", "xess": "XeSS", "ffx": "FSR 3/4"}),
        ]},
    ],
}

# ReShade's hotkeys are "virtual-key code,ctrl,shift,alt".
RESHADE = {
    "file": "ReShade.ini",
    "title": "ReShade (overlay)",
    "groups": [
        {"title": "Tasti", "fields": [
            _f("INPUT", "KeyOverlay", "Tasto per aprire l'overlay ReShade", "select",
               "Se HOME non funziona (tastiera compatta, conflitto col gioco) scegline un altro.",
               options={"36,0,0,0": "Home", "35,0,0,0": "Fine (End)", "34,0,0,0": "Pag giu'",
                        "113,0,1,0": "Shift + F2", "121,0,1,0": "Shift + F10",
                        "123,1,0,0": "Ctrl + F12"}, default="36,0,0,0"),
            _f("INPUT", "KeyEffects", "Tasto attiva/disattiva TUTTI gli effetti ReShade", "select",
               "Spegne ogni effetto ReShade. Per il solo DLSS 5 usa il 'Tasto confronto DLSS 5'.",
               options={"0,0,0,0": "Nessuno", "145,0,0,0": "Bloc Scorr (Scroll Lock)",
                        "119,0,1,0": "Shift + F8", "120,0,1,0": "Shift + F9"},
               default="0,0,0,0"),
        ]},
    ],
}

SCHEMAS = {"feeder": FEEDER, "optiscaler": OPTISCALER, "reshade": RESHADE}


def _fields(schema):
    for g in schema["groups"]:
        yield from g["fields"]


def read_values(schema: dict, exe_dir: Path) -> dict | None:
    """Current values from the game's file, or None if the file is not there."""
    path = exe_dir / schema["file"]
    if not path.exists():
        return None
    doc = IniDoc.load(path)
    out = {}
    for f in _fields(schema):
        v = doc.get(f["section"], f["key"])
        out[f"{f['section'] or ''}.{f['key']}"] = v if v is not None else f.get("default", "auto")
    return out


def write_values(schema: dict, exe_dir: Path, values: dict) -> list[str]:
    """Validate and write; returns the keys changed. Raises ValueError on bad input."""
    path = exe_dir / schema["file"]
    if not path.exists():
        raise ValueError(f"{schema['file']} non trovato: installa prima la route.")
    by_id = {f"{f['section'] or ''}.{f['key']}": f for f in _fields(schema)}
    doc, changed = IniDoc.load(path), []
    for fid, value in values.items():
        f = by_id.get(fid)
        if not f:
            raise ValueError(f"Parametro sconosciuto: {fid}")
        value = str(value).strip()
        if f["type"] == "select":
            if value not in f["options"]:
                raise ValueError(f"{f['label']}: valore non valido {value!r}")
        elif not (value == "auto" and f.get("auto")):
            try:
                num = float(value)
            except ValueError:
                raise ValueError(f"{f['label']}: non e' un numero: {value!r}") from None
            if not f["min"] <= num <= f["max"]:
                raise ValueError(f"{f['label']}: fuori intervallo {f['min']}..{f['max']}")
            value = str(int(num)) if float(f["step"]).is_integer() else f"{num:g}"
        if doc.get(f["section"], f["key"]) != value:
            doc.set(f["section"], f["key"], value)
            changed.append(fid)
    if changed:
        doc.save(path)
    return changed


def public(schema: dict) -> dict:
    return {"file": schema["file"], "title": schema["title"], "groups": [
        {**g, "fields": [{**f, "id": f"{f['section'] or ''}.{f['key']}"} for f in g["fields"]]}
        for g in schema["groups"]]}
