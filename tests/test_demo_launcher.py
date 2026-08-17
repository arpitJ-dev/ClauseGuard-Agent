from pathlib import Path

import pytest

from scripts.start_demo import resolve_data_dir


def test_runtime_reset_removes_only_dedicated_directory(tmp_path: Path):
    runtime = tmp_path / ".runtime-test"
    runtime.mkdir()
    (runtime / "jobs.db").write_text("test", encoding="utf-8")

    resolved = resolve_data_dir(".runtime-test", reset=True, root=tmp_path)

    assert resolved == runtime
    assert not runtime.exists()


@pytest.mark.parametrize("relative", [".", "reports", "../.runtime-outside"])
def test_runtime_reset_rejects_unsafe_targets(tmp_path: Path, relative: str):
    with pytest.raises(RuntimeError, match="Refusing to reset"):
        resolve_data_dir(relative, reset=True, root=tmp_path)


def test_runtime_reset_requires_an_explicit_directory(tmp_path: Path):
    with pytest.raises(RuntimeError, match="requires --data-dir"):
        resolve_data_dir(None, reset=True, root=tmp_path)
