from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = ("adiuvare/",)
RUNTIME_FILES = {"cli.py"}


def _git_lines(*args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if not base_ref:
        print("no base ref found, skipping changed-file policy check")
        return 0

    merge_base = _git_lines("merge-base", "HEAD", f"origin/{base_ref}")
    if not merge_base:
        print("could not resolve merge base, skipping changed-file policy check")
        return 0

    changed = _git_lines("diff", "--name-only", merge_base[0], "HEAD")
    runtime_changed = [
        path
        for path in changed
        if path in RUNTIME_FILES or any(path.startswith(root) for root in RUNTIME_ROOTS)
    ]
    tests_changed = [path for path in changed if path.startswith("tests/")]

    if not runtime_changed:
        print("no runtime code changes detected")
        return 0

    if tests_changed:
        print("runtime changes include tests")
        return 0

    print("runtime code changed without any matching test updates.")
    print("changed runtime files:")
    for path in runtime_changed:
        print(f"- {path}")
    print("please add or update tests for behavior changes.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
