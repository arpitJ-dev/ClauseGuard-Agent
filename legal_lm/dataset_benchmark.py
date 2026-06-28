from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List


class DatasetBenchmarkError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatasetPaths:
    root: Path
    original_dirs: tuple[Path, ...]
    perturbation_dirs: tuple[Path, ...]


def default_dataset_paths(root: str | Path = ".") -> DatasetPaths:
    base = Path(root).resolve()
    return DatasetPaths(
        root=base,
        original_dirs=(base / "Original_files", base / "Original and Modified"),
        perturbation_dirs=(base / "Perturbations", base / "Original and Modified"),
    )


def build_repo_dataset_benchmark(
    output_path: str | Path = "benchmarks/repo_dataset_benchmark.jsonl",
    inventory_path: str | Path = "docs/DATASET_INVENTORY.md",
    *,
    root: str | Path = ".",
) -> dict[str, Any]:
    paths = default_dataset_paths(root)
    json_files = _existing_files(paths.perturbation_dirs, "*.json")
    original_files = _index_files(_existing_files(paths.original_dirs, "*.txt") + _existing_files(paths.original_dirs, "*.pdf"))
    modified_files = _index_files(_existing_files(paths.perturbation_dirs, "modified_*"))

    if not json_files:
        raise DatasetBenchmarkError("No perturbation JSON files were found.")

    rows = []
    skipped = []
    perturbation_type_counter: Counter[str] = Counter()
    issue_counter: Counter[str] = Counter()
    perturbation_count = 0

    for json_file in json_files:
        payload = _read_json_list(json_file)
        for document_index, document_payload in enumerate(payload, start=1):
            source_name = str(document_payload.get("file_name") or "").strip()
            perturbations = document_payload.get("perturbation") or []
            if not source_name or not isinstance(perturbations, list):
                skipped.append({"json": str(json_file), "reason": "missing file_name or perturbation list"})
                continue

            original_path = _find_original(source_name, original_files)
            modified_path = _find_modified(json_file, source_name, modified_files)
            if not modified_path:
                skipped.append({"json": str(json_file), "source": source_name, "reason": "modified file not found"})
                continue

            expected_issue_types: set[str] = set()
            perturbation_summaries = []
            for perturbation in perturbations:
                if not isinstance(perturbation, dict):
                    continue
                perturbation_count += 1
                perturbation_type = str(perturbation.get("type") or "Unknown").strip()
                perturbation_type_counter[perturbation_type] += 1
                mapped_issues = _map_perturbation_to_issue_types(perturbation)
                expected_issue_types.update(mapped_issues)
                issue_counter.update(mapped_issues)
                perturbation_summaries.append(
                    {
                        "type": perturbation_type,
                        "location": str(perturbation.get("location") or "").strip(),
                        "expected_issue_types": sorted(mapped_issues),
                        "changed_text_preview": _preview(str(perturbation.get("changed_text") or "")),
                    }
                )

            if not expected_issue_types:
                skipped.append({"json": str(json_file), "source": source_name, "reason": "no mapped issue labels"})
                continue

            case_id = _case_id(source_name, document_index)
            rows.append(
                {
                    "id": case_id,
                    "document": _relative_for_manifest(modified_path, paths.root),
                    "description": f"Repo perturbation benchmark case derived from {source_name}.",
                    "expected_issue_types": sorted(expected_issue_types),
                    "expected_absent_issue_types": [],
                    "source_dataset": "repo_perturbations",
                    "original_document": _relative_for_manifest(original_path, paths.root) if original_path else None,
                    "perturbation_json": _relative_for_manifest(json_file, paths.root),
                    "perturbation_types": sorted({item["type"] for item in perturbation_summaries}),
                    "perturbations": perturbation_summaries,
                }
            )

    if not rows:
        raise DatasetBenchmarkError("No benchmark rows could be created from the repo dataset.")

    output = Path(output_path)
    if not output.is_absolute():
        output = paths.root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(row, ensure_ascii=True) for row in rows) + "\n", encoding="utf-8")

    inventory = {
        "original_file_count": len(_existing_files(paths.original_dirs, "*.txt")),
        "modified_file_count": len(_existing_files(paths.perturbation_dirs, "modified_*")),
        "perturbation_json_count": len(json_files),
        "perturbation_count": perturbation_count,
        "benchmark_case_count": len(rows),
        "skipped_count": len(skipped),
        "perturbation_types": dict(sorted(perturbation_type_counter.items())),
        "expected_issue_types": dict(sorted(issue_counter.items())),
        "benchmark_path": _relative_for_manifest(output, paths.root),
        "skipped": skipped,
    }

    inventory_target = Path(inventory_path)
    if not inventory_target.is_absolute():
        inventory_target = paths.root / inventory_target
    inventory_target.parent.mkdir(parents=True, exist_ok=True)
    inventory_target.write_text(_inventory_markdown(inventory), encoding="utf-8")
    return inventory


def _map_perturbation_to_issue_types(perturbation: dict[str, Any]) -> set[str]:
    perturbation_type = str(perturbation.get("type") or "").lower()
    changed = str(perturbation.get("changed_text") or "").lower()
    original = str(perturbation.get("original_text") or "").lower()
    explanation = str(perturbation.get("explanation") or "").lower()
    combined = f"{perturbation_type}\n{changed}\n{original}\n{explanation}"

    issues: set[str] = set()
    if "ambiguit" in perturbation_type:
        issues.add("risky_language")
    if "in text contradiction" in perturbation_type or "legal contradiction" in perturbation_type:
        issues.add("internal_contradiction")
    if "omission" in perturbation_type:
        issues.add("missing_required_language")
    if "misaligned terminology" in perturbation_type:
        issues.add("misaligned_terminology")
    if "structural flaw" in perturbation_type:
        issues.add("structural_flaw")

    if "assign" in changed and "without consent" in changed:
        issues.add("assignment_without_consent")
    if "terminate" in changed and "immediately" in changed and "notice" not in changed:
        issues.add("termination_without_notice")
    if "indemn" in changed and ("any and all" in changed or "without limitation" in changed):
        issues.add("uncapped_indemnity")
    if "payment" in changed and ("as agreed" in changed or "reasonable" in changed) and "days" not in changed:
        issues.add("vague_payment_terms")
    if any(term in changed for term in ["sole discretion", "as it sees fit", "deems appropriate", "at its discretion", "final say"]):
        issues.add("risky_language")
    if any(term in changed for term in ["as is", "exclusive remedy", "no liability", "unlimited"]):
        issues.add("risky_language")
    if "governing law" in combined and "omission" in perturbation_type:
        issues.add("missing_governing_law")

    return issues


def _existing_files(directories: Iterable[Path], pattern: str) -> List[Path]:
    files: List[Path] = []
    for directory in directories:
        if directory.exists():
            files.extend(path for path in directory.glob(pattern) if path.is_file())
    return sorted(files, key=lambda path: str(path).lower())


def _index_files(files: Iterable[Path]) -> dict[str, List[Path]]:
    indexed: dict[str, List[Path]] = {}
    for file_path in files:
        indexed.setdefault(_normalize_key(file_path.name), []).append(file_path)
    return indexed


def _find_original(source_name: str, original_files: dict[str, List[Path]]) -> Path | None:
    return _first_preferred(original_files.get(_normalize_key(source_name), []))


def _find_modified(json_file: Path, source_name: str, modified_files: dict[str, List[Path]]) -> Path | None:
    candidates = []
    candidates.extend(modified_files.get(_normalize_key(f"modified_{source_name}"), []))
    candidates.extend(modified_files.get(_normalize_key(json_file.name.replace("perturbed_", "modified_").removesuffix(".json")), []))
    candidates.extend(modified_files.get(_normalize_key(json_file.name.replace("perturbed_", "modified_").replace(".json", ".txt")), []))
    return _first_preferred(candidates)


def _first_preferred(paths: List[Path]) -> Path | None:
    if not paths:
        return None
    text_paths = [path for path in paths if path.suffix.lower() == ".txt"]
    return sorted(text_paths or paths, key=lambda path: len(path.name))[0]


def _normalize_key(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"^(modified_|perturbed_)", "", lowered)
    for suffix in [".json", ".txt", ".pdf"]:
        while lowered.endswith(suffix):
            lowered = lowered[: -len(suffix)]
    return re.sub(r"[^a-z0-9]+", "", lowered)


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetBenchmarkError(f"Invalid perturbation JSON: {path}") from exc
    if not isinstance(data, list):
        raise DatasetBenchmarkError(f"Perturbation JSON must contain a list: {path}")
    return data


def _relative_for_manifest(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _case_id(source_name: str, document_index: int) -> str:
    stem = Path(source_name).stem
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").lower()
    return f"repo_{document_index}_{cleaned[:80]}"


def _preview(text: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:limit]


def _inventory_markdown(inventory: dict[str, Any]) -> str:
    lines = [
        "# Dataset Inventory",
        "",
        "This inventory is generated from the repo's local contract perturbation dataset.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Original text files | {inventory['original_file_count']} |",
        f"| Modified files | {inventory['modified_file_count']} |",
        f"| Perturbation JSON files | {inventory['perturbation_json_count']} |",
        f"| Perturbation records | {inventory['perturbation_count']} |",
        f"| Benchmark cases generated | {inventory['benchmark_case_count']} |",
        f"| Skipped records | {inventory['skipped_count']} |",
        "",
        f"Benchmark manifest: `{inventory['benchmark_path']}`",
        "",
        "## Perturbation Types",
        "",
        "| Type | Count |",
        "|---|---:|",
    ]
    for perturbation_type, count in inventory["perturbation_types"].items():
        lines.append(f"| {perturbation_type} | {count} |")

    lines.extend(["", "## Expected Issue Labels", "", "| Issue Type | Count |", "|---|---:|"])
    for issue_type, count in inventory["expected_issue_types"].items():
        lines.append(f"| {issue_type} | {count} |")

    if inventory["skipped"]:
        lines.extend(["", "## Skipped", "", "| Source | Reason |", "|---|---|"])
        for item in inventory["skipped"]:
            source = item.get("source") or item.get("json") or "unknown"
            lines.append(f"| {source} | {item.get('reason', '')} |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Labels are mapped from perturbation metadata into the current Legal-LLM issue taxonomy.",
            "- Metrics from this dataset measure the current system against these mapped labels; they are not broad legal accuracy.",
            "- The benchmark can be run locally without API quota using `python -m legal_lm evaluate benchmarks\\repo_dataset_benchmark.jsonl --mock-models`.",
            "",
        ]
    )
    return "\n".join(lines)
