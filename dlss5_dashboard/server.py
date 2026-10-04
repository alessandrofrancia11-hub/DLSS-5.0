"""Local web server for the dashboard UI. Listens on 127.0.0.1 only.

Every /api call must carry the per-run token that is injected into the page,
and the Host header must be the local address: other websites open in the
browser can't drive the installer (CSRF / DNS rebinding).
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, backup, games, installers, jobs, launcher, settings_schema, store, sysinfo

WEB = Path(__file__).parent / "web"
TOKEN = secrets.token_urlsafe(24)
_SYSINFO: dict = {}
_SYSINFO_LOCK = threading.Lock()


def _sysinfo(refresh: bool = False) -> dict:
    with _SYSINFO_LOCK:
        if refresh or not _SYSINFO:
            _SYSINFO.clear()
            _SYSINFO.update(sysinfo.collect())
        return dict(_SYSINFO)


def _game_or_404(gid: str) -> dict:
    g = games.get(gid)
    if not g:
        raise LookupError("Gioco non trovato.")
    return g


def game_detail(gid: str) -> dict:
    a = games.analyze(_game_or_404(gid))
    state = store.load()
    manifest = state["manifests"].get(gid)
    a["prefs"] = state["prefs"].get(gid, {})
    a["install"] = None
    if manifest:
        a["install"] = {"route": manifest["route"], "added": manifest.get("added", []),
                        "changed": manifest.get("changed", []),
                        "backup_dir": manifest["backup_dir"],
                        "proxies": backup.proxies(manifest),
                        "enabled": backup.is_enabled(manifest)}
    a["settings"] = {}
    if a.get("exe_dir"):
        for key, schema in settings_schema.SCHEMAS.items():
            values = settings_schema.read_values(schema, Path(a["exe_dir"]))
            if values is not None:
                a["settings"][key] = {"schema": settings_schema.public(schema), "values": values}
    return a


# ------------------------------------------------------------------ API

def api_get(path: str, q: dict):
    if path == "/api/sysinfo":
        return _sysinfo(q.get("refresh") == "1")
    if path == "/api/games":
        return games.all_games()
    if path == "/api/game":
        return game_detail(q["id"])
    if path == "/api/job":
        j = jobs.get(q["id"])
        if not j:
            raise LookupError("Job non trovato.")
        return j
    if path == "/api/options":
        return {"consumers": installers.FEEDER_CONSUMERS,
                "opti_builds": {k: v["label"] for k, v in installers.OPTI_BUILDS.items()},
                "proxies": installers.PROXY_CHOICES, "version": __version__}
    raise LookupError("Endpoint sconosciuto.")


def api_post(path: str, body: dict):
    if path == "/api/games/add":
        return games.add_manual(body["exe"], body.get("name") or None)
    if path == "/api/games/remove":
        games.remove_manual(body["id"])
        return {"ok": True}
    if path == "/api/settings":
        g = games.analyze(_game_or_404(body["id"]))
        schema = settings_schema.SCHEMAS[body["file"]]
        return {"changed": settings_schema.write_values(schema, Path(g["exe_dir"]), body["values"])}
    if path == "/api/install":
        g = games.analyze(_game_or_404(body["id"]))
        if not g.get("exe"):
            raise ValueError("Eseguibile non trovato.")
        route = body["route"]
        fn = installers.ROUTES.get(route)
        if not fn:
            raise ValueError("Route sconosciuta.")
        return {"job": jobs.start(f"Installazione {route} - {g['name']}", fn, g,
                                  body.get("options", {}))}
    if path == "/api/restore":
        g = _game_or_404(body["id"])
        return {"job": jobs.start(f"Ripristino - {g['name']}", installers.restore, g)}
    if path == "/api/toggle":
        manifest = store.load()["manifests"].get(body["id"])
        if not manifest:
            raise ValueError("Nessuna installazione gestita.")
        return {"log": backup.set_enabled(manifest, bool(body["enabled"]))}
    if path == "/api/launch":
        g = games.analyze(_game_or_404(body["id"]))
        return {"log": launcher.launch(g, bool(body.get("dlss_on", True)), body.get("args", ""))}
    if path == "/api/open-folder":
        g = games.analyze(_game_or_404(body["id"]))
        launcher.open_folder(g.get("exe_dir") or g["install_dir"])
        return {"ok": True}
    raise LookupError("Endpoint sconosciuto.")


class Handler(BaseHTTPRequestHandler):
    server_version = "DLSS5Dashboard"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _api(self, fn, *args) -> None:
        if self.headers.get("X-Token") != TOKEN:
            return self._json(403, {"error": "Token non valido: ricarica la pagina."})
        try:
            self._json(200, fn(*args))
        except LookupError as e:
            self._json(404, {"error": str(e).strip("'")})
        except (ValueError, RuntimeError, OSError) as e:
            self._json(400, {"error": str(e)})

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        u = urlparse(self.path)
        if u.path.startswith("/api/"):
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            return self._api(api_get, u.path, q)
        name = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
        f = (WEB / name).resolve()
        if WEB.resolve() not in f.parents or not f.is_file():
            return self._send(404, b"not found", "text/plain")
        data = f.read_bytes()
        if f.name == "index.html":
            data = data.replace(b"__TOKEN__", TOKEN.encode())
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, data, ctype)

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json(400, {"error": "JSON non valido."})
        self._api(api_post, urlparse(self.path).path, body)


def serve(port: int = 8765, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"DLSS 5 Dashboard {__version__} in ascolto su {url}  (CTRL+C per chiudere)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Chiusa.")
