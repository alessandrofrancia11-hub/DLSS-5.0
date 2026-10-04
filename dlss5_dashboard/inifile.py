"""A small INI editor that changes values in place and keeps every comment.

configparser would rewrite OptiScaler.ini without its comments and choke on
dlss5-feed.cfg, which has no section header at all. Here section None means
the lines before the first [header].
"""
from __future__ import annotations

import re
from pathlib import Path

_HEADER = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _is_comment(line: str) -> bool:
    s = line.lstrip()
    return not s or s[0] in ";#"


class IniDoc:
    def __init__(self, text: str = "", newline: str = "\n"):
        self.lines = text.splitlines()
        self.newline = newline

    @classmethod
    def load(cls, path: Path) -> "IniDoc":
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return cls()
        text = raw.decode("utf-8-sig", errors="replace")
        return cls(text, "\r\n" if b"\r\n" in raw else "\n")

    def _bounds(self, section: str | None) -> tuple[int, int] | None:
        """[start, end) of the lines belonging to section (header excluded)."""
        start = 0 if section is None else None
        for i, line in enumerate(self.lines):
            m = _HEADER.match(line)
            if not m:
                continue
            if start is not None:
                return start, i
            if section is not None and m.group(1).strip().lower() == section.lower():
                start = i + 1
        return (start, len(self.lines)) if start is not None else None

    def _find(self, section: str | None, key: str) -> int | None:
        b = self._bounds(section)
        if not b:
            return None
        k = key.lower()
        for i in range(*b):
            line = self.lines[i]
            if _is_comment(line) or "=" not in line:
                continue
            if line.split("=", 1)[0].strip().lower() == k:
                return i
        return None

    def get(self, section: str | None, key: str, default: str | None = None) -> str | None:
        i = self._find(section, key)
        if i is None:
            return default
        return self.lines[i].split("=", 1)[1].strip()

    def set(self, section: str | None, key: str, value) -> None:
        value = _fmt(value)
        i = self._find(section, key)
        if i is not None:
            name = self.lines[i].split("=", 1)[0].strip()
            self.lines[i] = f"{name}={value}"
            return
        b = self._bounds(section)
        if b is None:
            if self.lines and self.lines[-1].strip():
                self.lines.append("")
            self.lines += [f"[{section}]", f"{key}={value}"]
            return
        start, end = b
        insert = end
        while insert > start and not self.lines[insert - 1].strip():
            insert -= 1
        self.lines.insert(insert, f"{key}={value}")

    def text(self) -> str:
        return self.newline.join(self.lines) + self.newline

    def save(self, path: Path) -> None:
        path.write_text(self.text(), encoding="utf-8", newline="")


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".") if v != int(v) else f"{v:.1f}"
    return str(v)
