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
SECRET_ASSIGNMENTS = (
    "EXECUTOR_PRIVATE_KEY",
    "DEMO_OWNER_PRIVATE_KEY",
    "ONEINCH_API_KEY",
    "ZEROX_API_KEY",
    "DATABASE_URL",
)
SELF = "scripts/validate_repo.py"
PROVIDER_DOCS = ("PRD.md", "AGENTS.md", "BUILD_RULES.md", "docs/ARCHITECTURE.md", "docs/INTEGRATIONS.md")


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    if missing:
        fail(f"Missing required source-of-truth files: {', '.join(missing)}")

    with (ROOT / "config/assets.schema.json").open("r", encoding="utf-8") as fh:
        json.load(fh)

    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    tracked_names = {Path(path).name for path in tracked}
    leaked = sorted(FORBIDDEN_TRACKED_NAMES & tracked_names)
    if leaked:
        fail(f"Forbidden secret file(s) tracked: {', '.join(leaked)}")

    # Scan line-by-line so an intentionally blank example cannot consume the next
    # line as its value. Any non-empty tracked secret assignment is a potential leak.
    for relative in tracked:
        if relative == SELF:
            continue
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            for key in SECRET_ASSIGNMENTS:
                prefix = f"{key}="
                if not stripped.startswith(prefix):
                    continue
                value = stripped[len(prefix):].strip()
                if value and relative != ".env.example":
                    fail(f"Potential committed {key} value in tracked file: {relative}")

    for relative in PROVIDER_DOCS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        if "1inch" not in text:
            fail(f"Provider source-of-truth drift: {relative} does not mention current 1inch path")

    print("Repository/source-of-truth baseline OK")


if __name__ == "__main__":
    main()
