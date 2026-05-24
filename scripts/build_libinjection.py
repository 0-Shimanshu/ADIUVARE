from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "adiuvare" / "vendor" / "libinjection_src"
OUT = ROOT / "adiuvare" / "vendor"


def _pick_gcc() -> str:
    if platform.system() != "Windows":
        return shutil.which("gcc") or "gcc"

    # Prefer the common 64-bit MSYS2 locations when they exist.
    candidates = [
        Path(r"C:\msys64\ucrt64\bin\gcc.exe"),
        Path(r"C:\msys64\mingw64\bin\gcc.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("gcc") or "gcc"


def build() -> None:
    needed = (
        SRC / "libinjection_sqli.c",
        SRC / "libinjection_html5.c",
        SRC / "libinjection_xss.c",
    )
    if any(not path.exists() for path in needed):
        raise FileNotFoundError(f"libinjection source files are missing from {SRC}")

    OUT.mkdir(parents=True, exist_ok=True)

    system = platform.system()
    cc = _pick_gcc()
    env = None
    if system == "Windows":
        env = dict(os.environ)
        # gcc often lives outside PATH when launched from a regular PowerShell.
        cc_dir = str(Path(cc).resolve().parent)
        env["PATH"] = cc_dir + ";" + env.get("PATH", "")
    if system == "Darwin":
        out_file = OUT / "libinjection.dylib"
        cmd = [
            cc,
            "-O2",
            "-fPIC",
            "-dynamiclib",
            str(SRC / "libinjection_sqli.c"),
            str(SRC / "libinjection_html5.c"),
            str(SRC / "libinjection_xss.c"),
            "-o",
            str(out_file),
        ]
    elif system == "Windows":
        out_file = OUT / "libinjection.dll"
        cmd = [
            cc,
            "-O2",
            "-shared",
            "-static",
            "-static-libgcc",
            str(SRC / "libinjection_sqli.c"),
            str(SRC / "libinjection_html5.c"),
            str(SRC / "libinjection_xss.c"),
            "-o",
            str(out_file),
        ]
    else:
        out_file = OUT / "libinjection.so"
        cmd = [
            cc,
            "-O2",
            "-fPIC",
            "-shared",
            str(SRC / "libinjection_sqli.c"),
            str(SRC / "libinjection_html5.c"),
            str(SRC / "libinjection_xss.c"),
            "-o",
            str(out_file),
        ]

    print(f"Using compiler: {cc}")
    print(f"Building library for {system}...")

    subprocess.run(cmd, check=True, env=env)

    print(f"Built successfully: {out_file}")

if __name__ == "__main__":
    build()
