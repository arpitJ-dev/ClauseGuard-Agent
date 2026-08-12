from __future__ import annotations

import os
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "SECURITY.md",
    ".env.example",
    ".gitignore",
    ".github/workflows/ci.yml",
    ".github/workflows/codeql.yml",
    ".github/dependabot.yml",
    "pyproject.toml",
    "requirements.txt",
    "clauseguard/__init__.py",
    "clauseguard/__main__.py",
    "clauseguard/pipeline.py",
    "docs/ARCHITECTURE.md",
    "docs/DATASET_INVENTORY.md",
    "docs/workbench.png",
    "data/README.md",
    "data/NOTICE.md",
    "apps/server/go.mod",
    "apps/web/package.json",
    "examples/demo_contract.txt",
    "examples/sample_report.md",
    "scripts/start_demo.py",
]

IGNORED_DIRS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".agents",
    ".codex",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "analysis_outputs",
    "test_outputs",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    "playwright-report",
    "test-results",
}

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"gsk_[0-9A-Za-z_\-]{20,}"),
    re.compile(r"gh[pousr]_[0-9A-Za-z]{36,255}"),
    re.compile(r"sk-[0-9A-Za-z_\-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}"),
    re.compile(r"-----BEGIN (?:EC |OPENSSH |RSA )?PRIVATE KEY-----"),
]

BRANDING_PATHS = [
    "README.md",
    ".env.example",
    ".gitignore",
    "requirements.txt",
    "clauseguard",
    "tests",
    "docs",
    "benchmarks",
    "scripts/smoke_groq.py",
]

DEPRECATED_IDENTIFIERS = (
    "legal" + "_lm",
    "LEGAL" + "_LM",
    "LegalAnalysis" + "Pipeline",
    "Legal" + "-LLM",
)

DEPRECATED_PUBLIC_PATHS = (
    "agents",
    "context_bank.py",
    "activate_venv.bat",
    "env_example.txt",
    "docs/GITHUB_RELEASE_CHECKLIST.md",
    "docs/RESUME_SUMMARY.md",
)

MAINTAINED_SOURCE_ROOTS = (
    "clauseguard",
    "apps/server",
    "apps/web/src",
    "scripts",
    "tests",
)


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
    failures.extend(scan_for_unpublished_source_files())

    failures.extend(scan_for_stale_branding())
    if (ROOT / ("legal" + "_lm")).exists():
        failures.append("Deprecated package directory still exists; use clauseguard/ only.")
    for relative in DEPRECATED_PUBLIC_PATHS:
        if (ROOT / relative).exists():
            failures.append(f"Deprecated public path still exists: {relative}")

    try:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        if metadata.get("project", {}).get("name") != "clauseguard-agent":
            failures.append("pyproject.toml must declare project.name = clauseguard-agent.")
        scripts = metadata.get("project", {}).get("scripts", {})
        if scripts.get("clauseguard") != "clauseguard.cli:main":
            failures.append("pyproject.toml must expose the clauseguard console command.")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        failures.append(f"Could not validate pyproject.toml: {exc}")

    if (ROOT / ".env").exists():
        warnings.append(".env exists locally; confirm it remains ignored before publishing.")

    version_artifacts = [
        path.name
        for path in ROOT.iterdir()
        if path.is_file() and re.fullmatch(r"\d+(?:\.\d+)*", path.name)
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


def scan_for_secrets(root: Path = ROOT) -> list[str]:
    hits: list[str] = []
    for path in scannable_files(root):
        relative = path.relative_to(root)
        if path.name == ".env":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"Possible secret in {relative}")
                break
    return hits


def scannable_files(root: Path):
    for current, directories, filenames in os.walk(root):
        directories[:] = [name for name in directories if not ignored_directory_name(name)]
        current_path = Path(current)
        for filename in filenames:
            yield current_path / filename


def ignored_directory_name(name: str) -> bool:
    return (
        name in IGNORED_DIRS
        or name.startswith(".runtime-")
        or name.startswith(".clauseguard")
        or name.endswith(".egg-info")
    )


def scan_for_unpublished_source_files(root: Path = ROOT) -> list[str]:
    if not (root / ".git").exists():
        return []

    failures: list[str] = []
    commands = (
        ("Untracked maintained source file", ["--others", "--exclude-standard"]),
        (
            "Ignored maintained source file",
            ["--others", "--ignored", "--exclude-standard"],
        ),
    )
    for label, arguments in commands:
        try:
            completed = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={root.as_posix()}",
                    "ls-files",
                    *arguments,
                    "--",
                    *MAINTAINED_SOURCE_ROOTS,
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            return [f"Could not inspect Git source tracking: {exc}"]
        if completed.returncode != 0:
            detail = completed.stderr.strip() or "git ls-files failed"
            return [f"Could not inspect Git source tracking: {detail}"]
        for value in completed.stdout.splitlines():
            relative = Path(value.strip())
            if value.strip() and not any(ignored_directory_name(part) for part in relative.parts):
                failures.append(f"{label}: {relative.as_posix()}")
    return sorted(failures)


def scan_for_stale_branding() -> list[str]:
    hits: list[str] = []
    for relative in BRANDING_PATHS:
        root = ROOT / relative
        paths = root.rglob("*") if root.is_dir() else [root]
        for path in paths:
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            found = [identifier for identifier in DEPRECATED_IDENTIFIERS if identifier in text]
            if found:
                rendered = ", ".join(found)
                hits.append(f"Stale project branding in {path.relative_to(ROOT)}: {rendered}")
    return hits


if __name__ == "__main__":
    raise SystemExit(main())
