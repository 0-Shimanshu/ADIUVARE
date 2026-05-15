from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTS = {".py", ".md", ".yml", ".yaml", ".toml", ".sql", ".txt"}
SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".verification_plan_run",
    "old",
    "document_for reference",
    "simulation",
}
PLACEHOLDERS = (
    "todo: implement",
    "your code here",
    "insert code here",
    "lorem ipsum",
)


def _git_lines(*args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _changed_files() -> list[Path]:
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if not base_ref:
        return []

    merge_base = _git_lines("merge-base", "HEAD", f"origin/{base_ref}")
    if not merge_base:
        return []

    files = _git_lines("diff", "--name-only", merge_base[0], "HEAD")
    return [ROOT / rel for rel in files]


def _walk_repo() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        files.append(path)
    return files


def _candidate_files() -> list[Path]:
    files = _changed_files() or _walk_repo()
    out: list[Path] = []
    for path in files:
        if not path.exists():
            continue
        if path == Path(__file__).resolve():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_EXTS:
            out.append(path)
    return out


def _line_issues(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="ignore")

    for lineno, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        if line.startswith("<<<<<<<") or line.startswith("=======") or line.startswith(">>>>>>>"):
            issues.append(f"{path.relative_to(ROOT)}:{lineno}: unresolved merge marker")
        for marker in PLACEHOLDERS:
            if marker in low:
                issues.append(f"{path.relative_to(ROOT)}:{lineno}: placeholder text '{marker}'")
    return issues


def main() -> int:
    issues: list[str] = []
    for path in _candidate_files():
        issues.extend(_line_issues(path))

    if not issues:
        print("repo hygiene check passed")
        return 0

    print("repo hygiene check found issues:")
    for item in issues:
        print(f"- {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
