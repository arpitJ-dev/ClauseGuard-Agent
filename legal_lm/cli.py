from __future__ import annotations

import argparse
import json
import sys

from legal_lm.config import ConfigError
from legal_lm.dataset_benchmark import DatasetBenchmarkError, build_repo_dataset_benchmark
from legal_lm.document import DocumentLoadError
from legal_lm.evaluation import EvaluationError, run_benchmark
from legal_lm.model_catalog import configured_model_rows
from legal_lm.model_router import ModelCallError
from legal_lm.pipeline import LegalAnalysisPipeline
from legal_lm.postprocessor import Postprocessor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Legal-LLM agentic contract analyzer.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze a legal document.")
    analyze.add_argument("document", help="Path to .txt, .docx, or .pdf document.")
    analyze.add_argument("--output-dir", default="analysis_outputs", help="Directory for report files.")
    analyze.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format to write.",
    )
    analyze.add_argument(
        "--mock-models",
        action="store_true",
        help="Run with deterministic mock model responses for tests/demo without API quota.",
    )

    models = subparsers.add_parser("models", help="Show configured model endpoints and local caps.")
    models.add_argument("--json", action="store_true", help="Print model configuration as JSON.")

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
        help="Run the benchmark without cloud model calls. This is the default.",
    )
    evaluate.add_argument(
        "--real-models",
        action="store_true",
        help="Use real Groq calls. Defaults to one case unless --max-cases is lower or an override is provided.",
    )
    evaluate.add_argument("--max-cases", type=int, help="Maximum number of benchmark cases to evaluate.")
    evaluate.add_argument(
        "--allow-multiple-real-cases",
        action="store_true",
        help="Allow real-model evaluation of more than one case after manually checking provider limits.",
    )

    dataset = subparsers.add_parser("build-dataset-benchmark", help="Build a benchmark from repo datasets.")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        formats = ("json", "markdown") if args.format == "both" else (args.format,)
        try:
            pipeline = LegalAnalysisPipeline.from_env(mock_models=args.mock_models)
            report = pipeline.analyze(args.document, output_dir=args.output_dir, output_formats=formats)
        except (ConfigError, DocumentLoadError, ModelCallError) as exc:
            print(f"Legal-LLM error: {exc}", file=sys.stderr)
            return 2

        print(Postprocessor().to_markdown(report))
        print(f"Reports written to: {args.output_dir}")
        return 0

    if args.command == "models":
        try:
            pipeline = LegalAnalysisPipeline.from_env(mock_models=True)
        except ConfigError as exc:
            print(f"Legal-LLM error: {exc}", file=sys.stderr)
            return 2

        rows = configured_model_rows(pipeline.config)
        if args.json:
            print(json.dumps(rows, indent=2))
            return 0

        print("Legal-LLM configured model endpoints")
        print("")
        for row in rows:
            print(f"{row['role']}: {row['provider']} / {row['model']}")
            print(f"  env: {row['env_var']}")
            print(f"  cap: {row['max_requests']} requests, {row['max_input_tokens']} estimated input tokens")
            print(f"  use: {row['purpose']}")
        return 0

    if args.command == "evaluate":
        if args.mock_models and args.real_models:
            print("Legal-LLM error: choose either --mock-models or --real-models, not both.", file=sys.stderr)
            return 2

        try:
            summary = run_benchmark(
                args.benchmark,
                output_dir=args.output_dir,
                mock_models=not args.real_models,
                max_cases=args.max_cases,
                allow_multiple_real_cases=args.allow_multiple_real_cases,
            )
        except (ConfigError, DocumentLoadError, ModelCallError, EvaluationError) as exc:
            print(f"Legal-LLM error: {exc}", file=sys.stderr)
            return 2

        aggregate = summary["aggregate"]
        print("Benchmark evaluation complete")
        print(f"Mode: {summary['mode']}")
        print(f"Cases evaluated: {summary['cases_evaluated']} of {summary['cases_available']}")
        print(
            "Precision: "
            f"{aggregate['precision']:.4f} | Recall: {aggregate['recall']:.4f} | F1: {aggregate['f1']:.4f}"
        )
        print(f"Results written to: {args.output_dir}")
        return 0

    if args.command == "build-dataset-benchmark":
        try:
            inventory = build_repo_dataset_benchmark(args.output, args.inventory)
        except DatasetBenchmarkError as exc:
            print(f"Legal-LLM error: {exc}", file=sys.stderr)
            return 2

        print("Repo dataset benchmark built")
        print(f"Benchmark cases: {inventory['benchmark_case_count']}")
        print(f"Perturbation records: {inventory['perturbation_count']}")
        print(f"Benchmark path: {inventory['benchmark_path']}")
        print(f"Inventory written to: {args.inventory}")
        return 0

    parser.print_help()
    return 1
