"""The two install routes.

feeder      Games without DLSS (e.g. Euro Truck Simulator 2). Runs DLSS5-Feeder's own
            PowerShell installer, downloaded from its official repository, in a
            console window you can watch and answer. It installs ReShade, the
            feeder, motion vectors and the neural add-on.
optiscaler  Games that ship DLSS. Downloads an OptiScaler DLSS-NR build from its
            GitHub release page and installs it as a proxy DLL.

Nothing is bundled here: every component comes from its publisher at install
time. Every install is wrapped in backup.begin()/finish() so it can be undone.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import backup, paths, store

UA = {"User-Agent": "dlss5-dashboard/0.1 (+local install helper)"}

FEEDER_INSTALLER_URL = ("https://raw.githubusercontent.com/jlrouzies-fr/DLSS5-Feeder/main/"
                        "tools/Install-DLSS5Feeder.ps1")
FEEDER_CONSUMERS = {"RenoDX": "RenoDX DLSS 5 add-on (consigliato dal Feeder)",
                    "OptiScaler": "OptiScaler DLSS-NR (wilsjo2)"}

OPTI_BUILDS = {
    "wilsjo2": {"label": "OptiScaler DLSS-NR (wilsjo2) - standard",
                "api": "https://api.github.com/repos/wilsjo2/OptiScaler-DLSSNR-PreSR-Multipass/releases?per_page=10",
                "want": (), "skip": ("rtx40-mfg",)},
    "wilsjo2-mfg": {"label": "OptiScaler DLSS-NR (wilsjo2) + sblocco MFG RTX 40",
                    "api": "https://api.github.com/repos/wilsjo2/OptiScaler-DLSSNR-PreSR-Multipass/releases?per_page=10",
                    "want": ("rtx40-mfg",), "skip": ()},
    "official": {"label": "OptiScaler ufficiale (senza DLSS 5)",
                 "api": "https://api.github.com/repos/optiscaler/OptiScaler/releases?per_page=10",
                 "want": (), "skip": ()},
}
PROXY_CHOICES = ("dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "d3d12.dll", "wininet.dll",
                 "winhttp.dll")

CREATE_NEW_CONSOLE = 0x00000010


# ------------------------------------------------------------------ helpers

def _download(url: str, dest: Path, job) -> Path:
    job.log(f"Scarico {url}")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    job.log(f"  -> {dest.name} ({dest.stat().st_size / 1e6:.1f} MB, sha256 {_sha256(dest)[:16]}...)")
    return dest


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _check_free(game_id: str) -> None:
    if store.load()["manifests"].get(game_id):
        raise ValueError("C'e' gia' un'installazione gestita per questo gioco: "
                         "ripristina (disinstalla) prima di installarne un'altra.")


def _save_manifest(game_id: str, manifest: dict) -> None:
    store.update(lambda s: s["manifests"].__setitem__(game_id, manifest))


def _validate_dlssnr(path: str | None) -> Path | None:
    if not path:
        return None
    p = Path(path.strip().strip('"'))
    if not p.is_file() or p.suffix.lower() != ".dll":
        raise ValueError(f"nvngx_dlssnr.dll non trovata: {path}")
    if p.stat().st_size < 50_000_000:
        raise ValueError("Il file indicato e' troppo piccolo per essere il modello neurale "
                         "(nvngx_dlssnr.dll pesa ~165 MB).")
    return p


# ------------------------------------------------------------------ feeder

def install_feeder(job, game: dict, opts: dict) -> dict:
    if os.name != "nt":
        raise RuntimeError("L'installer del Feeder gira solo su Windows.")
    _check_free(game["id"])
    exe = Path(game["exe"])
    consumer = opts.get("consumer", "RenoDX")
    if consumer not in FEEDER_CONSUMERS:
        raise ValueError(f"Consumer non valido: {consumer}")
    dlssnr = _validate_dlssnr(opts.get("dlssnr"))

    cache = paths.sub("downloads")
    ps1 = _download(FEEDER_INSTALLER_URL, cache / "Install-DLSS5Feeder.ps1", job)

    manifest = backup.begin(game["id"], str(exe.parent), "feeder")
    job.log(f"Backup di {len(manifest['saved'])} file in {manifest['backup_dir']}")

    args = [_ps_quote(exe), "-Consumer", consumer, "-HelperMode", "No"]
    if consumer == "OptiScaler":
        args += ["-OptiScalerFork", "wilsjo2"]
    if dlssnr:
        args += ["-DlssNrDll", _ps_quote(dlssnr)]
    wrapper = cache / "run-feeder-install.ps1"
    wrapper.write_text(
        "$Host.UI.RawUI.WindowTitle = 'DLSS 5 Dashboard - installazione DLSS5-Feeder'\n"
        "Write-Host 'Installer ufficiale DLSS5-Feeder. Rispondi alle domande qui sotto.' "
        "-ForegroundColor Cyan\n"
        f"& {_ps_quote(ps1)} {' '.join(args)}\n"
        "$code = $LASTEXITCODE\n"
        "Write-Host ''\n"
        "Read-Host \"Finito (codice $code). Premi INVIO per chiudere e tornare alla dashboard\"\n"
        "exit $code\n", encoding="utf-8-sig")
    job.log("Apro la finestra PowerShell dell'installer: segui le istruzioni li'.")
    proc = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                             str(wrapper)], cwd=str(exe.parent), creationflags=CREATE_NEW_CONSOLE)
    code = proc.wait()
    job.log(f"Installer terminato con codice {code}.")

    backup.finish(manifest)
    job.log(f"File aggiunti: {len(manifest['added'])}, modificati: {len(manifest['changed'])}")
    for a in manifest["added"][:40]:
        job.log(f"  + {a}")
    if not manifest["added"]:
        job.log("Nessun file aggiunto: l'installazione non e' andata a buon fine o e' stata annullata.")
        return {"installed": False}
    _save_manifest(game["id"], manifest)
    job.log("Fatto. Avvia il gioco dalla dashboard; in gioco HOME apre ReShade.")
    return {"installed": True}


# ------------------------------------------------------------------ optiscaler

def _github_json(url: str):
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def pick_asset(releases: list, want: tuple, skip: tuple) -> tuple[dict, dict, dict | None]:
    """Newest release carrying an OptiScaler package -> (release, asset, sha256 asset)."""
    for rel in releases:
        assets = rel.get("assets", [])
        for a in assets:
            n = a["name"].lower()
            if not n.endswith((".zip", ".7z")) or "optiscaler" not in n:
                continue
            if any(s in n for s in skip) or (want and not any(w in n for w in want)):
                continue
            sha = next((b for b in assets if b["name"].lower() == n + ".sha256"), None)
            return rel, a, sha
    raise RuntimeError("Nessuna release con un pacchetto OptiScaler adatto.")


def _extract(archive: Path, dest: Path) -> None:
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as z:
            for m in z.namelist():
                target = (dest / m).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    raise RuntimeError(f"Archivio con percorso sospetto: {m}")
            z.extractall(dest)
    else:  # .7z: Windows 10+ tar.exe (bsdtar) reads it
        subprocess.run(["tar", "-xf", str(archive), "-C", str(dest)], check=True)


def install_optiscaler(job, game: dict, opts: dict) -> dict:
    _check_free(game["id"])
    exe = Path(game["exe"])
    root = exe.parent
    build = OPTI_BUILDS.get(opts.get("build", "wilsjo2"))
    if not build:
        raise ValueError("Build OptiScaler non valida.")
    proxy = opts.get("proxy", "dxgi.dll").lower()
    if proxy not in PROXY_CHOICES:
        raise ValueError(f"Nome DLL non valido: {proxy}")
    if (root / proxy).exists():
        raise ValueError(f"{proxy} esiste gia' nella cartella del gioco (un altro mod?). "
                         "Scegli un altro nome DLL.")
    dlssnr = _validate_dlssnr(opts.get("dlssnr"))

    rel, asset, sha = pick_asset(_github_json(build["api"]), build["want"], build["skip"])
    job.log(f"Release {rel['tag_name']}: {asset['name']}")
    cache = paths.sub("downloads")
    arc = _download(asset["browser_download_url"], cache / asset["name"], job)
    if sha:
        expected = urllib.request.urlopen(urllib.request.Request(
            sha["browser_download_url"], headers=UA), timeout=30).read().decode().split()[0].lower()
        if expected != _sha256(arc):
            arc.unlink()
            raise RuntimeError("SHA-256 non corrisponde a quello pubblicato: download scartato.")
        job.log("SHA-256 verificato.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _extract(arc, tmp)
        dll = next((p for p in tmp.rglob("*") if p.name.lower() == "optiscaler.dll"), None)
        if not dll:
            raise RuntimeError("OptiScaler.dll non trovato nell'archivio.")
        pkg = dll.parent

        manifest = backup.begin(game["id"], str(root), "optiscaler")
        job.log(f"Backup di {len(manifest['saved'])} file in {manifest['backup_dir']}")
        try:
            for src in pkg.rglob("*"):
                if src.is_dir() or src.name.lower() in ("setup_windows.bat", "setup_linux.sh"):
                    continue
                rel_path = src.relative_to(pkg)
                dst = root / (proxy if src == dll else rel_path)
                if dst.exists() and len(rel_path.parts) > 1:
                    job.log(f"  salto {rel_path} (esiste gia')")
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            if dlssnr:
                shutil.copy2(dlssnr, root / "nvngx_dlssnr.dll")
                job.log("nvngx_dlssnr.dll copiata accanto al gioco.")
        except OSError:
            job.log("Copia fallita: annullo le modifiche.")
            backup.restore(backup.finish(manifest))
            raise
        job.log(f"OptiScaler installato come {proxy}")
    backup.finish(manifest)
    _save_manifest(game["id"], manifest)
    job.log(f"Fatto: {len(manifest['added'])} file aggiunti. In gioco INSERT apre OptiScaler.")
    return {"installed": True}


# ------------------------------------------------------------------ restore

def restore(job, game: dict) -> dict:
    manifest = store.load()["manifests"].get(game["id"])
    if not manifest:
        raise ValueError("Nessuna installazione gestita dalla dashboard per questo gioco.")
    for line in backup.restore(manifest):
        job.log(line)
    store.update(lambda s: s["manifests"].pop(game["id"], None))
    job.log("Gioco riportato allo stato originale.")
    return {"restored": True}


ROUTES = {"feeder": install_feeder, "optiscaler": install_optiscaler}
