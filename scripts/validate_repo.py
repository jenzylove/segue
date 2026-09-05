from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "README.md",
    "PRD.md",
    "BUILD_RULES.md",
    "AGENTS.md",
    ".gitignore",
    ".env.example",
    "docs/ARCHITECTURE.md",
    "docs/INTEGRATIONS.md",
    "config/assets.schema.json",
]

FORBIDDEN_TRACKED_NAMES = {".env", ".env.local", ".env.production", ".env.development"}
SECRET_MARKERS = (
    "ZEROX_API_KEY=0x",
    "EXECUTOR_PRIVATE_KEY=0x",
    "DATABASE_URL=postgresql://",
)


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    if missing:
        fail(f"Missing required M0 files: {', '.join(missing)}")

    with (ROOT / "config/assets.schema.json").open("r", encoding="utf-8") as fh:
        json.load(fh)

    tracked = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True
    ).splitlines()
    tracked_names = {Path(path).name for path in tracked}
    leaked = sorted(FORBIDDEN_TRACKED_NAMES & tracked_names)
    if leaked:
        fail(f"Forbidden secret file(s) tracked: {', '.join(leaked)}")

    for relative in tracked:
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in SECRET_MARKERS:
            if marker in text and relative != ".env.example":
                fail(f"Potential secret marker in tracked file: {relative}")

    print("M0 repository baseline OK")


if __name__ == "__main__":
    main()
