import json
from pathlib import Path

import pytest

from clauseguard.cli import SCHEMA_MODELS, main
from clauseguard.exit_codes import ExitCode


def test_models_command_emits_json(capsys):
    exit_code = main(["models", "--json"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert {row["role"] for row in output} == {
        "extraction",
        "reasoning",
        "embedding",
        "verifier",
    }


def test_models_command_emits_human_readable_configuration(capsys):
    exit_code = main(["models"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "ClauseGuard configured model endpoints" in output
    assert "extraction:" in output


def test_analyze_command_writes_reports_in_mock_mode(tmp_path: Path, capsys):
    document = tmp_path / "agreement.txt"
    document.write_text(
        "SERVICES AGREEMENT\n\n1. Payment. Customer shall pay within thirty days.",
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"

    exit_code = main(
        [
            "analyze",
            str(document),
            "--mock-models",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "analysis_report.json").exists()
    assert (output_dir / "analysis_report.md").exists()
    assert "Reports written to" in capsys.readouterr().out


def test_analyze_command_returns_clean_error_for_missing_document(tmp_path: Path, capsys):
    exit_code = main(["analyze", str(tmp_path / "missing.txt"), "--mock-models"])

    captured = capsys.readouterr()
    assert exit_code == ExitCode.DOCUMENT
    assert "Document not found" in captured.err


def test_analyze_command_emits_versioned_progress_events(tmp_path: Path, capsys):
    document = tmp_path / "agreement.txt"
    document.write_text(
        "SERVICES AGREEMENT\n\n1. Payment. Customer shall pay within thirty days.",
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"

    exit_code = main(
        [
            "analyze",
            str(document),
            "--mock-models",
            "--events-jsonl",
            "--format",
            "json",
            "--run-id",
            "analysis-test-1",
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.out.splitlines()]
    assert exit_code == ExitCode.SUCCESS
    assert captured.err == ""
    assert events[0]["stage"] == "queued"
    assert events[-1]["type"] == "completed"
    assert events[-1]["run_id"] == "analysis-test-1"
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert {event["stage"] for event in events} >= {
        "loading",
        "extracting",
        "retrieving",
        "checking",
        "verifying",
        "scoring",
        "rewriting",
        "reporting",
        "completed",
    }
    assert all(event["schema_version"] == "1.0" for event in events)
    report = json.loads((output_dir / "analysis_report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == "1.0"
    assert report["document_id"] == "analysis-test-1"


def test_analyze_event_stream_reports_typed_document_error(tmp_path: Path, capsys):
    exit_code = main(
        [
            "analyze",
            str(tmp_path / "missing.txt"),
            "--mock-models",
            "--events-jsonl",
            "--run-id",
            "missing-document",
        ]
    )

    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.out.splitlines()]
    assert exit_code == ExitCode.DOCUMENT
    assert events[-1]["type"] == "error"
    assert events[-1]["error"]["code"] == "document_error"
    assert events[-1]["details"]["exit_code"] == ExitCode.DOCUMENT
    assert "Document not found" in captured.err


def test_evaluate_rejects_conflicting_model_modes(capsys):
    exit_code = main(["evaluate", "--mock-models", "--real-models"])

    assert exit_code == 2
    assert "choose either" in capsys.readouterr().err


def test_compare_command_writes_comparison_report(tmp_path: Path, capsys):
    original = tmp_path / "original.txt"
    modified = tmp_path / "modified.txt"
    original.write_text(
        "SUPPLY AGREEMENT\n\n1. Assignment. Neither party may assign without consent.",
        encoding="utf-8",
    )
    modified.write_text(
        "SUPPLY AGREEMENT\n\n1. Assignment. Supplier may assign without consent.",
        encoding="utf-8",
    )
    output_dir = tmp_path / "comparison"

    exit_code = main(["compare", str(original), str(modified), "--output-dir", str(output_dir)])

    assert exit_code == 0
    assert (output_dir / "comparison_report.json").exists()
    assert "Comparison complete" in capsys.readouterr().out


def test_compare_command_emits_machine_events(tmp_path: Path, capsys):
    original = tmp_path / "original.txt"
    modified = tmp_path / "modified.txt"
    original.write_text(
        "SUPPLY AGREEMENT\n\n1. Assignment. Neither party may assign without consent.",
        encoding="utf-8",
    )
    modified.write_text(
        "SUPPLY AGREEMENT\n\n1. Assignment. Supplier may assign without consent.",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "compare",
            str(original),
            str(modified),
            "--events-jsonl",
            "--format",
            "json",
            "--run-id",
            "comparison-test-1",
            "--output-dir",
            str(tmp_path / "comparison"),
        ]
    )

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert exit_code == ExitCode.SUCCESS
    assert events[-1]["type"] == "completed"
    assert events[-1]["details"]["comparison_id"] == "comparison-test-1"
    assert "comparing" in {event["stage"] for event in events}
    assert (tmp_path / "comparison" / "comparison_report.json").exists()
    assert not (tmp_path / "comparison" / "comparison_report.md").exists()


@pytest.mark.parametrize(
    ("schema_name", "expected_title"),
    [
        ("analysis-report", "AnalysisReport"),
        ("comparison-report", "ComparisonReport"),
        ("progress-event", "ProgressEvent"),
    ],
)
def test_schema_command_exports_versioned_contract(
    tmp_path: Path, schema_name: str, expected_title: str
):
    output = tmp_path / f"{schema_name}.schema.json"

    exit_code = main(["schema", schema_name, "--output", str(output)])

    schema = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == ExitCode.SUCCESS
    assert schema["title"] == expected_title
    assert schema["properties"]["schema_version"]["const"] == "1.0"


@pytest.mark.parametrize(
    ("schema_name", "filename"),
    [
        ("analysis-report", "analysis-report-v1.schema.json"),
        ("comparison-report", "comparison-report-v1.schema.json"),
        ("progress-event", "progress-event-v1.schema.json"),
    ],
)
def test_committed_json_schema_matches_runtime_contract(schema_name: str, filename: str):
    schema_path = Path(__file__).resolve().parents[1] / "contracts" / "schemas" / filename
    committed = json.loads(schema_path.read_text(encoding="utf-8"))

    assert committed == SCHEMA_MODELS[schema_name].model_json_schema()


def test_evaluate_command_runs_local_benchmark(tmp_path: Path, capsys):
    document = tmp_path / "contract.txt"
    document.write_text(
        "SERVICES AGREEMENT\n\n1. Payment. Fees are due within thirty days.",
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.jsonl"
    benchmark.write_text(
        '{"id":"case-1","document":"contract.txt",'
        '"expected_issue_types":["missing_governing_law"]}\n',
        encoding="utf-8",
    )

    exit_code = main(
        [
            "evaluate",
            str(benchmark),
            "--mock-models",
            "--output-dir",
            str(tmp_path / "evaluation"),
        ]
    )

    assert exit_code == 0
    assert "Benchmark evaluation complete" in capsys.readouterr().out


def test_build_dataset_benchmark_command_writes_requested_files(tmp_path: Path, capsys):
    output = tmp_path / "repo_benchmark.jsonl"
    inventory = tmp_path / "inventory.md"

    exit_code = main(
        [
            "build-dataset-benchmark",
            "--output",
            str(output),
            "--inventory",
            str(inventory),
        ]
    )

    assert exit_code == 0
    assert output.exists()
    assert inventory.exists()
    assert "Repo dataset benchmark built" in capsys.readouterr().out
