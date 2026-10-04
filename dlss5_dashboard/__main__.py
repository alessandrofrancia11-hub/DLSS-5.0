"""python -m dlss5_dashboard [serve|sysinfo|games]"""
from __future__ import annotations

import argparse
import json

from . import games, server, sysinfo


def main() -> None:
    ap = argparse.ArgumentParser(prog="dlss5_dashboard", description="DLSS 5 Dashboard")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="avvia la dashboard (predefinito)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    i = sub.add_parser("sysinfo", help="mostra le informazioni di sistema")
    i.add_argument("--json", action="store_true")
    sub.add_parser("games", help="elenca i giochi trovati")
    a = ap.parse_args()

    if a.cmd == "sysinfo":
        info = sysinfo.collect()
        print(json.dumps(info, indent=2, ensure_ascii=False) if a.json else sysinfo.format_text(info))
    elif a.cmd == "games":
        for g in games.all_games():
            print(f"{g['name']:<45} {g['id']:<20} {g['install_dir']}")
    else:
        server.serve(getattr(a, "port", 8765), not getattr(a, "no_browser", False))


if __name__ == "__main__":
    main()
