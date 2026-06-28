from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    ".env.example",
    ".gitignore",
    "requirements.txt",
    "legal_lm/__main__.py",
    "legal_lm/pipeline.py",
    "docs/ARCHITECTURE.md",
    "docs/RESUME_SUMMARY.md",
    "docs/GITHUB_RELEASE_CHECKLIST.md",
    "examples/demo_contract.txt",
    "examples/sample_report.md",
]

IGNORED_DIRS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".agents",
    ".codex",
    "__pycache__",
    "venv",
    "env",
    "analysis_outputs",
    "test_outputs",
}

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"gsk_[0-9A-Za-z_\-]{20,}"),
    re.compile(r"sk-[0-9A-Za-z_\-]{20,}"),
    re.compile(r"eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}"),
]


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).exists():
            failures.append(f"Missing required file: {relative}")

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8", errors="ignore")
    for required_pattern in [".env", "venv/", "test_outputs/", "analysis_outputs/", "*.zip"]:
        if required_pattern not in gitignore:
            failures.append(f".gitignore should include: {required_pattern}")

    secret_hits = scan_for_secrets()
    failures.extend(secret_hits)

    if (ROOT / ".env").exists():
        warnings.append(".env exists locally. This is okay only because it is ignored; rotate keys before public release.")

    version_artifacts = [
        path.name for path in ROOT.iterdir() if path.is_file() and re.fullmatch(r"\d+(?:\.\d+)*", path.name)
    ]
    if version_artifacts and "/[0-9]*" not in gitignore:
        warnings.append(
            "Root install/version artifacts should be ignored or removed before publishing: "
            + ", ".join(sorted(version_artifacts))
        )

    for message in failures:
        print(f"[FAIL] {message}")
    for message in warnings:
        print(f"[WARN] {message}")

    if not failures:
        print("[OK] Publish readiness checks passed.")
        return 0
    return 1


def scan_for_secrets() -> list[str]:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.name == ".env":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"Possible secret in {path.relative_to(ROOT)}")
                break
    return hits


if __name__ == "__main__":
    raise SystemExit(main())
