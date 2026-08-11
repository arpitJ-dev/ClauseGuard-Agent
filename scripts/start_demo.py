"""Build and run the ClauseGuard browser demo from a clean checkout."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "apps" / "web"
SERVER_DIR = ROOT / "apps" / "server"


def executable(name: str) -> str:
    candidates = [name]
    if os.name == "nt":
        candidates.insert(0, f"{name}.cmd")
        candidates.insert(0, f"{name}.exe")
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        standard_locations = {
            "go": program_files / "Go" / "bin" / "go.exe",
            "npm": program_files / "nodejs" / "npm.cmd",
        }
        standard = standard_locations.get(name)
        if standard and standard.is_file():
            return str(standard)
    raise RuntimeError(f"Required executable is not available: {name}")


def run_checked(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def resolve_data_dir(value: str | None, reset: bool, root: Path = ROOT) -> Path | None:
    if not value:
        if reset:
            raise RuntimeError("--reset-data requires --data-dir.")
        return None

    data_dir = Path(value)
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    data_dir = data_dir.resolve()
    if reset:
        safe_name = data_dir.name == ".clauseguard" or data_dir.name.startswith(
            (".clauseguard-", ".runtime-")
        )
        if root.resolve() not in data_dir.parents or not safe_name:
            raise RuntimeError("Refusing to reset a non-dedicated ClauseGuard runtime directory.")
        if data_dir.exists():
            shutil.rmtree(data_dir)
    return data_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ClauseGuard full-stack demo.")
    parser.add_argument(
        "--live-models",
        action="store_true",
        help="Use configured cloud models instead of deterministic demo responses.",
    )
    parser.add_argument(
        "--address",
        default="127.0.0.1:8080",
        help="HTTP listen address (default: 127.0.0.1:8080).",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Do not install frontend packages when node_modules is absent.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Use the existing production frontend bundle.",
    )
    parser.add_argument(
        "--data-dir",
        help="Runtime data directory, relative to the repository unless absolute.",
    )
    parser.add_argument(
        "--reset-data",
        action="store_true",
        help="Clear the configured runtime data directory before startup.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    npm = executable("npm")
    go = executable("go")

    node_modules = WEB_DIR / "node_modules"
    if not node_modules.is_dir():
        if args.skip_install:
            raise RuntimeError("Frontend packages are missing; run npm ci in apps/web.")
        run_checked([npm, "ci"], WEB_DIR)

    bundle = WEB_DIR / "dist" / "index.html"
    if args.skip_build:
        if not bundle.is_file():
            raise RuntimeError("Frontend bundle is missing; run npm run build in apps/web.")
    else:
        run_checked([npm, "run", "build"], WEB_DIR)

    environment = os.environ.copy()
    environment["CLAUSEGUARD_WORKSPACE"] = str(ROOT)
    environment["CLAUSEGUARD_WEB_DIR"] = str(WEB_DIR / "dist")
    environment["CLAUSEGUARD_MOCK_MODELS"] = "false" if args.live_models else "true"

    environment["CLAUSEGUARD_SERVER_ADDR"] = args.address

    data_dir = resolve_data_dir(args.data_dir, args.reset_data)
    if data_dir is not None:
        environment["CLAUSEGUARD_DATA_DIR"] = str(data_dir)

    mode = "configured cloud models" if args.live_models else "deterministic demo models"
    print(f"ClauseGuard is starting at http://{args.address} ({mode}).", flush=True)
    completed = subprocess.run(
        [go, "run", "./cmd/clauseguard-server"],
        cwd=SERVER_DIR,
        env=environment,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ClauseGuard could not start: {error}", file=sys.stderr)
        raise SystemExit(1) from error
