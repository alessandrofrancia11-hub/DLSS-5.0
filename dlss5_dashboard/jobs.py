"""Long-running work (downloads, installs) in background threads, with a log the UI polls."""
from __future__ import annotations

import threading
import time
import traceback
import uuid

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


class Job:
    def __init__(self, rec: dict):
        self.rec = rec

    def log(self, msg: str) -> None:
        with _LOCK:
            self.rec["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")


def start(title: str, fn, *args) -> str:
    jid = uuid.uuid4().hex[:10]
    rec = {"id": jid, "title": title, "status": "running", "log": [], "result": None}
    with _LOCK:
        _JOBS[jid] = rec
    job = Job(rec)

    def run():
        try:
            rec["result"] = fn(job, *args)
            rec["status"] = "done"
        except Exception as e:  # shown to the user, not swallowed
            job.log(f"ERRORE: {e}")
            if not isinstance(e, (ValueError, RuntimeError)):
                job.log(traceback.format_exc())
            rec["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return jid


def get(jid: str) -> dict | None:
    with _LOCK:
        rec = _JOBS.get(jid)
        return {**rec, "log": list(rec["log"])} if rec else None
