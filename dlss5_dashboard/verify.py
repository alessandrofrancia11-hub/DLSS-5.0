"""Reads ReShade.log / dlss5-feed.log and says whether DLSS 5 neural rendering really ran.

The RenoDX DLSS 5 add-on prints a verdict line every 30 s and at shutdown:
    NR-VERDICT v3 state=ENGAGED ... evals=182309 ratio=0.9999 ...
    NR cost: gpu_ms=11.42 ... (estimate: 190 fps without NR, 60 fps with it)
The newest of those is what the last game session did.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

TAIL_BYTES = 4 * 1024 * 1024

_VERDICT = re.compile(r"NR-VERDICT\b.*?state=(\w+).*?evals=(\d+)\s+ratio=([\d.]+)")
_COST = re.compile(r"NR cost: gpu_ms=([\d.]+).*?estimate: (\d+) fps without NR, (\d+) fps with it")
_FPS = re.compile(r"telemetry .*?\bfps=([\d.]+)")
_RES = re.compile(r"frame contract .*?\bin=(\d+x\d+)")
_WARN = re.compile(r"NR-WARN summary active=(\d+)")
_REFUSED = re.compile(r"0xbad00001|feature 18 create failed", re.I)


def _tail(path: Path) -> list[str]:
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        return f.read().decode("utf-8", errors="replace").splitlines()


def _last(rx: re.Pattern, lines: list[str]):
    for line in reversed(lines):
        m = rx.search(line)
        if m:
            return m
    return None


_OPTI_OK = re.compile(r"DLSS-NR.*(feature created at|feature up at|model initialised|running natively)", re.I)
_OPTI_BAD = re.compile(r"DLSS-NR.*(failed|refused|could not|unavailable|not possible)|CreateFeature\(18\) failed", re.I)
_OPTI_TOGGLE = re.compile(r"Neural Rendering key pressed", re.I)


def check_optiscaler(exe_dir: str | Path) -> dict:
    """Same verdict for the OptiScaler route, from OptiScaler.log."""
    d = Path(exe_dir)
    log = d / "OptiScaler.log"
    out = {"level": "warn", "title": "", "facts": [], "hints": [], "log_time": None}
    if not log.exists():
        out["title"] = "Nessun OptiScaler.log"
        out["hints"] = ["OptiScaler scrive il log solo se 'Log su file' e' attivo: accendilo nella sezione "
                        "OptiScaler qui sotto, gioca qualche minuto e riprova.",
                        "Verifica veloce senza log: in gioco premi INSERT. Se compare il menu OptiScaler "
                        "e' caricato; nella sezione 'DLSS Neural Rendering' sotto la casella c'e' lo stato."]
        return out
    lines = _tail(log)
    out["log_time"] = time.strftime("%d/%m %H:%M", time.localtime(log.stat().st_mtime))
    ok, bad = _last(_OPTI_OK, lines), _last(_OPTI_BAD, lines)
    toggles = sum(1 for line in lines if _OPTI_TOGGLE.search(line))
    if ok:
        out["facts"].append(("Modello neurale", ok.string.strip()[-140:]))
    if bad:
        out["facts"].append(("Ultimo errore DLSS-NR", bad.string.strip()[-140:]))
    if toggles:
        out["facts"].append(("Pressioni tasto Neural Rendering", str(toggles)))
    if ok and (not bad or lines.index(ok.string) > lines.index(bad.string)):
        out["level"], out["title"] = "ok", "OptiScaler caricato, DLSS 5 neurale creato"
    elif bad:
        out["level"], out["title"] = "warn", "OptiScaler caricato, DLSS 5 neurale non partito"
        out["hints"].append("Controlla in gioco (INSERT) che 'Enable Neural Rendering' sia acceso e leggi "
                            "il motivo scritto sotto la casella.")
    else:
        out["level"], out["title"] = "warn", "OptiScaler caricato, nessun dato DLSS-NR nel log"
        out["hints"].append("Accendi 'Neural Rendering' (INSERT in gioco o qui sotto), gioca e riprova.")
    return out


def check(exe_dir: str | Path, route: str | None = None) -> dict:
    if route == "optiscaler":
        return check_optiscaler(exe_dir)
    d = Path(exe_dir)
    log = d / "ReShade.log"
    out = {"level": "error", "title": "", "facts": [], "hints": [], "log_time": None}
    if not log.exists():
        out["title"] = "ReShade non si e' mai caricato"
        out["hints"] = ["Nessun ReShade.log accanto al gioco: controlla che dxgi.dll ci sia e che il "
                        "gioco parta in DirectX 11/12 (non OpenGL).",
                        "Controlla che l'interruttore DLSS 5 sia su ON."]
        return out

    lines = _tail(log)
    age = time.time() - log.stat().st_mtime
    out["log_time"] = time.strftime("%d/%m %H:%M", time.localtime(log.stat().st_mtime))
    verdict, cost = _last(_VERDICT, lines), _last(_COST, lines)
    fps, res, warn = _last(_FPS, lines), _last(_RES, lines), _last(_WARN, lines)
    refused = _last(_REFUSED, lines)

    if res:
        out["facts"].append(("Risoluzione elaborata", res.group(1)))
    if verdict:
        out["facts"].append(("Stato modello neurale", verdict.group(1)))
        out["facts"].append(("Frame elaborati", f"{int(verdict.group(2)):,} "
                                                f"({float(verdict.group(3)) * 100:.2f}%)".replace(",", ".")))
    if cost:
        out["facts"].append(("Costo DLSS 5 neurale", f"{float(cost.group(1)):.1f} ms per frame"))
        out["facts"].append(("FPS stimati", f"{cost.group(3)} con DLSS 5 / {cost.group(2)} senza"))
    if fps:
        out["facts"].append(("FPS misurati", f"{float(fps.group(1)):.0f}"))
    if warn and int(warn.group(1)):
        out["hints"].append(f"L'add-on segnala {warn.group(1)} avvisi attivi: guarda ReShade.log.")

    if verdict and verdict.group(1).upper() == "ENGAGED":
        out["level"], out["title"] = "ok", "DLSS 5 neurale attivo"
        if cost and int(cost.group(3)) < 55:
            out["hints"].append("Sotto i 60 fps: abbassa la 'Risoluzione di lavoro neurale' o la "
                                "risoluzione del gioco.")
    elif refused:
        out["level"], out["title"] = "warn", "Solo DLAA: la GPU rifiuta il modello neurale"
        out["hints"].append("nvngx_dlssnr.dll ha rifiutato la scheda (0xbad00001). Serve una build "
                            "compatibile con la tua GPU.")
    elif verdict:
        out["level"], out["title"] = "warn", f"Modello neurale non attivo (stato {verdict.group(1)})"
        out["hints"].append("Controlla che Neural Rendering sia acceso nella scheda Add-ons di ReShade.")
    else:
        out["level"], out["title"] = "warn", "ReShade attivo, nessun dato DLSS 5 nel log"
        out["hints"].append("Gioca almeno un minuto con DLSS 5 attivo, chiudi il gioco e riprova.")

    if age > 6 * 3600:
        out["hints"].append(f"Il log e' del {out['log_time']}: riflette l'ultima sessione, non quella attuale.")
    return out
