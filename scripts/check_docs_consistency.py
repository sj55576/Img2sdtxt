"""Check that the public configuration and API documentation stays current."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _config_variables() -> set[str]:
    text = (ROOT / "config.py").read_text(encoding="utf-8")
    return set(re.findall(r'os\.getenv\("([A-Z][A-Z0-9_]*)"', text))


def _env_example_variables() -> set[str]:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", text, flags=re.MULTILINE))


def _documented_variables(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"`([A-Z][A-Z0-9_]*)`", text))


def main() -> int:
    config_variables = _config_variables()
    env_variables = _env_example_variables()
    errors: list[str] = []

    missing_from_env = sorted(config_variables - env_variables)
    if missing_from_env:
        errors.append(f".env.example is missing config variables: {', '.join(missing_from_env)}")

    for name in ("README.md", "README-ja.md"):
        path = ROOT / name
        documented = _documented_variables(path)
        missing = sorted(config_variables - documented)
        if missing:
            errors.append(f"{name} is missing config variables: {', '.join(missing)}")

        text = path.read_text(encoding="utf-8")
        for required in ("/metrics", "/api/jobs/queue/stats", "/api/cache/stats", "routes/", "providers/"):
            if required not in text:
                errors.append(f"{name} is missing required documentation marker: {required}")
        if "Python 3.10+" not in text:
            errors.append(f"{name} must state Python 3.10+")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"Documentation consistency check passed ({len(config_variables)} config variables).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
