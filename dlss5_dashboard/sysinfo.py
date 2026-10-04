"""Reads the PC's hardware and says what DLSS 5 can do on its NVIDIA card."""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess

# compute capability -> (architecture, series)
ARCHS = {
    "7.5": ("Turing", "RTX 20"),
    "8.6": ("Ampere", "RTX 30"),
    "8.7": ("Ampere", "RTX 30"),
    "8.9": ("Ada Lovelace", "RTX 40"),
    "10.0": ("Blackwell", "RTX 50"),
    "12.0": ("Blackwell", "RTX 50"),
}

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


def _run(cmd: list[str], timeout: int = 20) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=_NO_WINDOW)
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    if os.name == "nt":
        for p in (r"C:\Windows\System32\nvidia-smi.exe",
                  r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
            if os.path.exists(p):
                return p
    return None


def parse_nvidia_smi(text: str) -> list[dict]:
    """Rows of `name, driver, vram MiB, compute cap` -> dicts."""
    gpus = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4 or not parts[0]:
            continue
        name, driver, vram, cc = parts[:4]
        arch, series = ARCHS.get(cc, ("sconosciuta", "?"))
        try:
            vram_mb = int(float(vram))
        except ValueError:
            vram_mb = None
        gpus.append({"name": name, "driver": driver, "vram_mb": vram_mb,
                     "compute_cap": cc, "arch": arch, "series": series})
    return gpus


def nvidia_gpus() -> list[dict]:
    exe = _nvidia_smi()
    if not exe:
        return []
    return parse_nvidia_smi(_run([exe, "--query-gpu=name,driver_version,memory.total,compute_cap",
                                  "--format=csv,noheader,nounits"]))


_PS_INFO = (
    "$o=[ordered]@{"
    "os=(Get-CimInstance Win32_OperatingSystem).Caption;"
    "build=(Get-CimInstance Win32_OperatingSystem).BuildNumber;"
    "cpu=(Get-CimInstance Win32_Processor | Select-Object -First 1).Name;"
    "ram=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;"
    "adapters=@(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name })"
    "}; $o | ConvertTo-Json -Compress"
)


def _windows_info() -> dict:
    out = _run(["powershell", "-NoProfile", "-Command", _PS_INFO])
    try:
        d = json.loads(out)
    except ValueError:
        return {}
    ram = d.get("ram")
    return {
        "os": f"{d.get('os', '')} (build {d.get('build', '?')})".strip(),
        "cpu": (d.get("cpu") or "").strip(),
        "ram_gb": round(int(ram) / 1024 ** 3, 1) if ram else None,
        "adapters": d.get("adapters") or [],
    }


def _generic_info() -> dict:
    ram_gb = None
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    ram_gb = round(int(line.split()[1]) / 1024 ** 2, 1)
    except OSError:
        pass
    return {"os": f"{platform.system()} {platform.release()}",
            "cpu": platform.processor() or platform.machine(),
            "ram_gb": ram_gb, "adapters": []}


def assess(gpu: dict | None) -> dict:
    """What DLSS 5 neural rendering means on this card, in plain words."""
    if not gpu:
        return {"level": "none",
                "title": "Nessuna GPU NVIDIA rilevata",
                "detail": "DLSS gira solo su GPU NVIDIA RTX con driver installato (nvidia-smi)."}
    series = gpu["series"]
    if series == "RTX 50":
        return {"level": "native",
                "title": "DLSS 5 supportato ufficialmente",
                "detail": "Le RTX 50 eseguono il modello neurale di NVIDIA (nvngx_dlssnr.dll) senza modifiche."}
    if series == "RTX 40":
        return {"level": "community",
                "title": "DLSS 5 neurale: solo con DLL modificata (non ufficiale)",
                "detail": ("NVIDIA ha promesso il supporto RTX 40 ma senza data. Oggi la nvngx_dlssnr.dll "
                           "firmata rifiuta le RTX 40 (errore 0xbad00001): serve una build modificata "
                           "dalla community. Senza, funzionano comunque DLSS SR/DLAA, i preset del "
                           "transformer e (nei giochi con DLSS-G) la Frame Generation, anche multipla "
                           "con lo sblocco MFG.")}
    if series in ("RTX 20", "RTX 30"):
        return {"level": "limited",
                "title": "DLSS 5 neurale: solo con DLL modificata, prestazioni basse",
                "detail": "DLSS SR/DLAA funzionano; il passaggio neurale e' molto pesante su queste schede."}
    return {"level": "none", "title": "GPU non riconosciuta",
            "detail": f"Compute capability {gpu.get('compute_cap')} non in tabella."}


def collect() -> dict:
    base = _windows_info() if os.name == "nt" else {}
    if not base:
        base = _generic_info()
    gpus = nvidia_gpus()
    primary = gpus[0] if gpus else None
    return {**base, "gpus": gpus, "dlss5": assess(primary)}


def format_text(info: dict) -> str:
    lines = [f"Sistema operativo : {info.get('os')}",
             f"CPU               : {info.get('cpu')}",
             f"RAM               : {info.get('ram_gb')} GB"]
    for g in info.get("gpus", []):
        lines.append(f"GPU               : {g['name']} ({g['series']}, {g['arch']}, "
                     f"{g['vram_mb']} MB VRAM), driver {g['driver']}")
    if not info.get("gpus"):
        for a in info.get("adapters", []):
            lines.append(f"Scheda video      : {a}")
    d = info["dlss5"]
    lines += ["", f"DLSS 5: {d['title']}", f"  {d['detail']}"]
    return "\n".join(lines)
