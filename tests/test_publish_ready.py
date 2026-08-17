import subprocess
from pathlib import Path

import pytest

from scripts.check_publish_ready import scan_for_secrets, scan_for_unpublished_source_files


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + ("a" * 36),
        "AKIA" + ("A" * 16),
        "-----BEGIN " + "PRIVATE KEY-----",
    ],
)
def test_secret_scan_detects_common_repository_credentials(tmp_path: Path, secret: str):
    source = tmp_path / "settings.txt"
    source.write_text(secret, encoding="utf-8")

    assert scan_for_secrets(tmp_path) == ["Possible secret in settings.txt"]


def test_secret_scan_finds_source_file_and_skips_dependency_tree(tmp_path: Path):
    source = tmp_path / "service.py"
    source.write_text("TOKEN = 'gsk_" + ("a" * 24) + "'", encoding="utf-8")
    dependency = tmp_path / "node_modules" / "package" / "index.js"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("gsk_" + ("b" * 24), encoding="utf-8")

    hits = scan_for_secrets(tmp_path)

    assert hits == ["Possible secret in service.py"]


def test_secret_scan_checks_large_source_files(tmp_path: Path):
    source = tmp_path / "large-source.txt"
    source.write_bytes((b"x" * (5 * 1024 * 1024)) + ("gsk_" + ("c" * 24)).encode())

    assert scan_for_secrets(tmp_path) == ["Possible secret in large-source.txt"]


def test_publish_scan_detects_untracked_and_ignored_source_files(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("lib/\n", encoding="utf-8")
    ignored = tmp_path / "apps" / "web" / "src" / "lib" / "format.ts"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("export const score = 1;\n", encoding="utf-8")
    untracked = tmp_path / "clauseguard" / "new_agent.py"
    untracked.parent.mkdir()
    untracked.write_text("VALUE = 1\n", encoding="utf-8")

    assert scan_for_unpublished_source_files(tmp_path) == [
        "Ignored maintained source file: apps/web/src/lib/format.ts",
        "Untracked maintained source file: clauseguard/new_agent.py",
    ]
