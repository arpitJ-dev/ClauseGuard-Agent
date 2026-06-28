from __future__ import annotations

from pathlib import Path
from typing import Iterable

from legal_lm.context import ContextBank
from legal_lm.schemas import AnalysisReport


class Postprocessor:
    def build_report(self, context: ContextBank) -> AnalysisReport:
        if not context.document:
            raise ValueError("Cannot build report before a document is loaded.")

        accepted = [finding for finding in context.findings if finding.accepted]
        high = sum(1 for finding in accepted if finding.severity == "HIGH")
        summary = (
            f"Analyzed {len(context.clauses)} clauses and accepted {len(accepted)} evidence-backed findings "
            f"({high} high severity)."
        )
        return AnalysisReport(
            document_id=context.document_id,
            file_path=context.document.path,
            title=context.document.title,
            document_type=context.document_type,
            summary=summary,
            clauses=context.clauses,
            entities=context.entities,
            evidence=context.evidence,
            findings=context.findings,
            rewrites=context.rewrites,
        )

    def to_markdown(self, report: AnalysisReport) -> str:
        lines = [
            f"# Legal-LLM Analysis Report",
            "",
            f"**Document:** {report.title}",
            f"**Type:** {report.document_type}",
            f"**Generated:** {report.generated_at}",
            "",
            "## Summary",
            "",
            report.summary,
            "",
            "## Findings",
            "",
        ]
        accepted_findings = [finding for finding in report.findings if finding.accepted]
        if not accepted_findings:
            lines.append("No accepted findings were detected.")
        for finding in accepted_findings:
            lines.extend(
                [
                    f"### {finding.severity}: {finding.issue_type}",
                    "",
                    f"- Clause: {finding.clause_title or finding.clause_id or 'Document-level'}",
                    f"- Final score: {finding.component_scores.final:.2f}",
                    f"- Primary model confidence: {finding.model_confidence:.2f}",
                    f"- Verifier confidence: {finding.verifier_confidence:.2f}",
                    f"- Explanation: {finding.explanation}",
                    f"- Evidence: {self._evidence_titles(finding.evidence)}",
                    "",
                ]
            )
            if finding.suggested_rewrite:
                lines.extend(["Suggested rewrite:", "", finding.suggested_rewrite, ""])

        lines.extend(["## Limitations", ""])
        lines.extend(f"- {item}" for item in report.limitations)
        lines.append("")
        return "\n".join(lines)

    def write_outputs(self, report: AnalysisReport, output_dir: str | Path, formats: Iterable[str]) -> None:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        selected = set(formats)
        if "json" in selected:
            (target / "analysis_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        if "markdown" in selected:
            (target / "analysis_report.md").write_text(self.to_markdown(report), encoding="utf-8")

    def _evidence_titles(self, evidence) -> str:
        if not evidence:
            return "No supporting local reference retrieved."
        return ", ".join(item.title for item in evidence[:3])
