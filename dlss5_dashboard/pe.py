"""Just enough of the PE format to tell a game's bitness and graphics API."""
from __future__ import annotations

import struct
from pathlib import Path

MACHINES = {0x14C: "x86", 0x8664: "x64", 0xAA64: "arm64"}

API_BY_DLL = (
    ("d3d12.dll", "D3D12"),
    ("vulkan-1.dll", "Vulkan"),
    ("d3d11.dll", "D3D11"),
    ("d3d10.dll", "D3D10"),
    ("d3d10_1.dll", "D3D10"),
    ("d3d9.dll", "D3D9"),
    ("d3d8.dll", "D3D8"),
    ("opengl32.dll", "OpenGL"),
)


def _cstr(data: bytes, off: int) -> str:
    end = data.find(b"\0", off, off + 512)
    return data[off:end if end != -1 else off + 512].decode("ascii", "replace")


def read_pe(path: str | Path) -> dict:
    """{"machine": "x64"|"x86"|..., "imports": [lowercase dll names]}; empty on failure."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return {"machine": None, "imports": []}
    try:
        return _parse(data)
    except (struct.error, IndexError, ValueError):
        return {"machine": None, "imports": []}


def _parse(data: bytes) -> dict:
    if data[:2] != b"MZ":
        raise ValueError("not MZ")
    e = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e:e + 4] != b"PE\0\0":
        raise ValueError("not PE")
    machine, nsec = struct.unpack_from("<HH", data, e + 4)
    opt_size = struct.unpack_from("<H", data, e + 20)[0]
    opt = e + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x10B:
        ndirs, dirs = struct.unpack_from("<I", data, opt + 92)[0], opt + 96
    elif magic == 0x20B:
        ndirs, dirs = struct.unpack_from("<I", data, opt + 108)[0], opt + 112
    else:
        raise ValueError("bad optional header")

    sections = []
    s = opt + opt_size
    for i in range(nsec):
        vsize, va, rsize, raw = struct.unpack_from("<IIII", data, s + i * 40 + 8)
        sections.append((va, max(vsize, rsize), raw))

    def off(rva: int) -> int:
        for va, size, raw in sections:
            if va <= rva < va + size:
                return rva - va + raw
        raise ValueError("rva outside sections")

    imports: list[str] = []
    if ndirs > 1:
        rva = struct.unpack_from("<I", data, dirs + 8)[0]
        if rva:
            p = off(rva)
            for _ in range(4096):
                name_rva = struct.unpack_from("<I", data, p + 12)[0]
                if not any(data[p:p + 20]):
                    break
                if name_rva:
                    imports.append(_cstr(data, off(name_rva)).lower())
                p += 20
    if ndirs > 13:  # delay-load imports
        rva = struct.unpack_from("<I", data, dirs + 13 * 8)[0]
        if rva:
            p = off(rva)
            for _ in range(4096):
                if not any(data[p:p + 32]):
                    break
                attrs, name_rva = struct.unpack_from("<II", data, p)
                if name_rva and attrs & 1:
                    imports.append(_cstr(data, off(name_rva)).lower())
                p += 32
    return {"machine": MACHINES.get(machine, hex(machine)), "imports": imports}


def guess_api(imports: list[str]) -> str | None:
    names = set(imports)
    for dll, api in API_BY_DLL:
        if dll in names:
            return api
    return None
