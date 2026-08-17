from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from clauseguard.comparison import compare_documents
from clauseguard.dataset_benchmark import build_repo_dataset_benchmark
from clauseguard.evaluation import run_benchmark
from clauseguard.events import JsonLineEventWriter, ProgressEvent
from clauseguard.exit_codes import ExitCode, classify_exception
from clauseguard.model_catalog import configured_model_rows
from clauseguard.pipeline import ClauseGuardPipeline
from clauseguard.postprocessor import Postprocessor
from clauseguard.schemas import AnalysisReport, ComparisonReport

SCHEMA_MODELS: dict[str, Type[BaseModel]] = {
    "analysis-report": AnalysisReport,
    "comparison-report": ComparisonReport,
    "progress-event": ProgressEvent,
}


def _add_machine_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable success output.",
    )
    parser.add_argument(
        "--events-jsonl",
        action="store_true",
        help="Emit versioned NDJSON progress events to stdout; implies --quiet.",
    )
    parser.add_argument(
        "--run-id",
        help="Caller-supplied run identifier for job correlation.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ClauseGuard Agent contract analyzer.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze a legal document.")
    analyze.add_argument("document", help="Path to .txt, .docx, or .pdf document.")
    analyze.add_argument(
        "--output-dir", default="analysis_outputs", help="Directory for report files."
    )
    analyze.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format to write.",
    )
    analyze.add_argument(
        "--mock-models",
        action="store_true",
        help="Use deterministic model fixtures for repeatable local analysis.",
    )
    _add_machine_options(analyze)

    models = subparsers.add_parser("models", help="Show configured model roles and safety limits.")
    models.add_argument("--json", action="store_true", help="Print model configuration as JSON.")

    compare = subparsers.add_parser(
        "compare",
        help="Compare two document versions and report clause-level changes.",
    )
    compare.add_argument("original", help="Path to the original .txt, .docx, or .pdf document.")
    compare.add_argument("modified", help="Path to the modified .txt, .docx, or .pdf document.")
    compare.add_argument(
        "--output-dir",
        default="analysis_outputs/comparison",
        help="Directory for comparison report files.",
    )
    compare.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format to write.",
    )
    compare.add_argument(
        "--real-models",
        action="store_true",
        help="Use configured hosted models during preprocessing.",
    )
    _add_machine_options(compare)

    evaluate = subparsers.add_parser("evaluate", help="Run labeled benchmark evaluation.")
    evaluate.add_argument(
        "benchmark",
        nargs="?",
        default="benchmarks/seed_contracts.jsonl",
        help="Path to a JSONL benchmark file.",
    )
    evaluate.add_argument(
        "--output-dir",
        default="analysis_outputs/benchmark_evaluation",
        help="Directory for benchmark result files.",
    )
    evaluate.add_argument(
        "--mock-models",
        action="store_true",
        help="Use deterministic model fixtures. This is the default.",
    )
    evaluate.add_argument(
        "--real-models",
        action="store_true",
        help="Use configured hosted models. Defaults to one case.",
    )
    evaluate.add_argument(
        "--max-cases", type=int, help="Maximum number of benchmark cases to evaluate."
    )
    evaluate.add_argument(
        "--allow-multiple-real-cases",
        action="store_true",
        help="Allow hosted-model evaluation of more than one case.",
    )

    dataset = subparsers.add_parser(
        "build-dataset-benchmark", help="Build a benchmark from repo datasets."
    )
    dataset.add_argument(
        "--output",
        default="benchmarks/repo_dataset_benchmark.jsonl",
        help="Benchmark JSONL path to write.",
    )
    dataset.add_argument(
        "--inventory",
        default="docs/DATASET_INVENTORY.md",
        help="Dataset inventory Markdown path to write.",
    )

    schema = subparsers.add_parser(
        "schema", help="Export a versioned machine-readable JSON Schema."
    )
    schema.add_argument("name", choices=sorted(SCHEMA_MODELS), help="Schema to export.")
    schema.add_argument("--output", help="File path to write instead of stdout.")
    return parser


def _event_writer(args: argparse.Namespace, run_id: str) -> JsonLineEventWriter | None:
    if not getattr(args, "events_jsonl", False):
        return None
    return JsonLineEventWriter(sys.stdout, run_id)


def _emit_queued(writer: JsonLineEventWriter | None, command: str) -> None:
    if writer is None:
        return
    writer.emit(
        event_type="progress",
        stage="queued",
        status="queued",
        progress=0,
        message=f"{command.capitalize()} job accepted",
        details={"command": command},
    )


def _return_error(exc: BaseException, writer: JsonLineEventWriter | None = None) -> int:
    exit_code, error_code = classify_exception(exc)
    message = str(exc)
    if exit_code == ExitCode.INTERNAL:
        message = f"Unexpected internal error ({type(exc).__name__})."
    if exit_code == ExitCode.CANCELLED:
        message = "Operation cancelled."

    if writer is not None:
        writer.failed(error_code, message, details={"exit_code": int(exit_code)})
    print(f"ClauseGuard error: {message}", file=sys.stderr)
    return int(exit_code)


def _analysis_report_files(output_dir: str | Path, formats: tuple[str, ...]) -> list[str]:
    names = {"json": "analysis_report.json", "markdown": "analysis_report.md"}
    target = Path(output_dir)
    return [str(target / names[format_name]) for format_name in formats]


def _comparison_report_files(output_dir: str | Path, formats: tuple[str, ...]) -> list[str]:
    names = {"json": "comparison_report.json", "markdown": "comparison_report.md"}
    target = Path(output_dir)
    return [str(target / names[format_name]) for format_name in formats]


def _write_schema(name: str, output: str | None) -> None:
    payload = SCHEMA_MODELS[name].model_json_schema()
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(encoded)
        return

    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(encoded, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        formats = ("json", "markdown") if args.format == "both" else (args.format,)
        run_id = args.run_id or str(uuid.uuid4())
        writer = _event_writer(args, run_id)
        _emit_queued(writer, "analysis")
        try:
            pipeline = ClauseGuardPipeline.from_env(mock_models=args.mock_models)
            report = pipeline.analyze(
                args.document,
                output_dir=args.output_dir,
                output_formats=formats,
                run_id=run_id,
                progress_callback=writer.progress if writer else None,
            )
        except KeyboardInterrupt as exc:
            return _return_error(exc, writer)
        except Exception as exc:
            return _return_error(exc, writer)

        report_files = _analysis_report_files(args.output_dir, formats)
        if writer is not None:
            writer.completed(
                "Analysis completed",
                {
                    "document_id": report.document_id,
                    "report_files": report_files,
                    "accepted_findings": sum(1 for finding in report.findings if finding.accepted),
                },
            )

        if not (args.quiet or args.events_jsonl):
            print(Postprocessor().to_markdown(report))
            print(f"Reports written to: {args.output_dir}")
        return int(ExitCode.SUCCESS)

    if args.command == "models":
        try:
            pipeline = ClauseGuardPipeline.from_env(mock_models=True)
        except Exception as exc:
            return _return_error(exc)

        rows = configured_model_rows(pipeline.config)
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0

        print("ClauseGuard configured model endpoints")
        print("")
        for row in rows:
            print(f"{row['role']}: {row['provider']} / {row['model']}")
            print(f"  env: {row['env_var']}")
            print(
                f"  cap: {row['max_requests']} requests, {row['max_input_tokens']} estimated input tokens"
            )
            print(f"  use: {row['purpose']}")
        return int(ExitCode.SUCCESS)

    if args.command == "compare":
        formats = ("json", "markdown") if args.format == "both" else (args.format,)
        run_id = args.run_id or str(uuid.uuid4())
        writer = _event_writer(args, run_id)
        _emit_queued(writer, "comparison")
        try:
            comparison = compare_documents(
                args.original,
                args.modified,
                output_dir=args.output_dir,
                output_formats=formats,
                mock_models=not args.real_models,
                comparison_id=run_id,
                progress_callback=writer.progress if writer else None,
            )
        except KeyboardInterrupt as exc:
            return _return_error(exc, writer)
        except Exception as exc:
            return _return_error(exc, writer)

        summary = comparison["summary"]
        if writer is not None:
            writer.completed(
                "Comparison completed",
                {
                    "comparison_id": comparison["comparison_id"],
                    "report_files": _comparison_report_files(args.output_dir, formats),
                    "summary": summary,
                    "risk_signal_count": len(comparison["risk_signals"]),
                },
            )

        if not (args.quiet or args.events_jsonl):
            print("Comparison complete")
            print(
                f"Matched: {summary['matched']} | Changed: {summary['changed']} | "
                f"Added: {summary['added']} | Removed: {summary['removed']}"
            )
            print(f"Risk signals: {len(comparison['risk_signals'])}")
            print(f"Results written to: {args.output_dir}")
        return int(ExitCode.SUCCESS)

    if args.command == "evaluate":
        if args.mock_models and args.real_models:
            print(
                "ClauseGuard error: choose either --mock-models or --real-models, not both.",
                file=sys.stderr,
            )
            return int(ExitCode.USAGE)

        try:
            summary = run_benchmark(
                args.benchmark,
                output_dir=args.output_dir,
                mock_models=not args.real_models,
                max_cases=args.max_cases,
                allow_multiple_real_cases=args.allow_multiple_real_cases,
            )
        except KeyboardInterrupt as exc:
            return _return_error(exc)
        except Exception as exc:
            return _return_error(exc)

        aggregate = summary["aggregate"]
        print("Benchmark evaluation complete")
        print(f"Mode: {summary['mode']}")
        print(f"Cases evaluated: {summary['cases_evaluated']} of {summary['cases_available']}")
        print(
            "Precision: "
            f"{aggregate['precision']:.4f} | Recall: {aggregate['recall']:.4f} | F1: {aggregate['f1']:.4f}"
        )
        print(f"Results written to: {args.output_dir}")
        return int(ExitCode.SUCCESS)

    if args.command == "build-dataset-benchmark":
        try:
            inventory = build_repo_dataset_benchmark(args.output, args.inventory)
        except KeyboardInterrupt as exc:
            return _return_error(exc)
        except Exception as exc:
            return _return_error(exc)

        print("Repo dataset benchmark built")
        print(f"Benchmark cases: {inventory['benchmark_case_count']}")
        print(f"Perturbation records: {inventory['perturbation_count']}")
        print(f"Benchmark path: {inventory['benchmark_path']}")
        print(f"Inventory written to: {args.inventory}")
        return int(ExitCode.SUCCESS)

    if args.command == "schema":
        try:
            _write_schema(args.name, args.output)
        except KeyboardInterrupt as exc:
            return _return_error(exc)
        except Exception as exc:
            return _return_error(exc)
        return int(ExitCode.SUCCESS)

    parser.print_help()
    return int(ExitCode.USAGE)
