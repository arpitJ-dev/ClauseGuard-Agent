import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  Info,
  ListChecks,
  Scale,
  ShieldAlert,
  WandSparkles,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { AnalysisReport, Finding, Severity } from "../api/types";
import { formatScore, humanize } from "../lib/format";

type AnalysisTab = "findings" | "clauses" | "rewrites" | "audit";
type SeverityFilter = "ALL" | Severity;

interface AnalysisReportViewProps {
  report: AnalysisReport;
  onDownload: () => void;
}

const scoreRows: Array<[keyof Finding["component_scores"], string]> = [
  ["deterministic_rules", "Rule confidence"],
  ["rag_evidence", "Evidence relevance"],
  ["primary_reasoning", "Reasoning confidence"],
  ["verifier_agreement", "Verifier agreement"],
  ["clause_structure", "Document consistency"],
];

function FindingCard({
  finding,
  expanded,
  onToggle,
}: {
  finding: Finding;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <article className={`finding-card severity-border-${finding.severity.toLowerCase()}`}>
      <button className="finding-header" type="button" onClick={onToggle} aria-expanded={expanded}>
        <span className={`severity-badge severity-${finding.severity.toLowerCase()}`}>
          {finding.severity}
        </span>
        <span className="finding-title">
          <strong>{humanize(finding.issue_type)}</strong>
          <small>{finding.clause_title ?? "Document level"}</small>
        </span>
        <span className="finding-score">
          <strong>{formatScore(finding.component_scores.final)}</strong>
          <small>decision score</small>
        </span>
        {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>

      {expanded ? (
        <div className="finding-body">
          <p className="finding-explanation">{finding.explanation}</p>
          <dl className="finding-metadata">
            <div>
              <dt>Rule</dt>
              <dd>{finding.rule_id || "Model-assisted review"}</dd>
            </div>
            <div>
              <dt>Threshold</dt>
              <dd>{formatScore(finding.acceptance_threshold ?? 0.55)}</dd>
            </div>
            <div>
              <dt>Verifier</dt>
              <dd>{humanize(finding.verifier_status ?? "not_run")}</dd>
            </div>
          </dl>

          {finding.signals?.length ? (
            <div className="signal-list" aria-label="Detected signals">
              {finding.signals.map((signal) => (
                <span key={signal}>{signal}</span>
              ))}
            </div>
          ) : null}

          <div className="finding-detail-grid">
            <section className="score-breakdown" aria-labelledby={`score-${finding.id}`}>
              <h4 id={`score-${finding.id}`}>Score breakdown</h4>
              {scoreRows.map(([key, label]) => {
                const value = finding.component_scores[key];
                if (typeof value !== "number") return null;
                return (
                  <div className="score-row" key={key}>
                    <span>{label}</span>
                    <progress
                      className="mini-track"
                      max={1}
                      value={value}
                      aria-label={`${label}: ${formatScore(value)}`}
                    />
                    <strong>{formatScore(value)}</strong>
                  </div>
                );
              })}
            </section>

            <section className="evidence-section" aria-labelledby={`evidence-${finding.id}`}>
              <h4 id={`evidence-${finding.id}`}>Supporting evidence</h4>
              {finding.evidence?.length ? (
                <ul className="evidence-list">
                  {finding.evidence.map((evidence) => (
                    <li key={evidence.id}>
                      <span>
                        <strong>{evidence.title}</strong>
                        <small>{evidence.text}</small>
                      </span>
                      <b>{formatScore(evidence.relevance)}</b>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted-copy">No evidence attached</p>
              )}
            </section>
          </div>

          {finding.verifier_rationale ? (
            <div className="verifier-note">
              <Scale size={16} />
              <span>{finding.verifier_rationale}</span>
            </div>
          ) : null}

          {finding.suggested_rewrite ? (
            <section className="inline-rewrite">
              <h4>
                <WandSparkles size={16} />
                Suggested revision
              </h4>
              <p>{finding.suggested_rewrite}</p>
            </section>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

export function AnalysisReportView({ report, onDownload }: AnalysisReportViewProps) {
  const [tab, setTab] = useState<AnalysisTab>("findings");
  const [severity, setSeverity] = useState<SeverityFilter>("ALL");
  const [expandedFinding, setExpandedFinding] = useState<string | null>(report.findings[0]?.id ?? null);

  const acceptedFindings = useMemo(
    () => report.findings.filter((finding) => finding.accepted),
    [report.findings],
  );
  const visibleFindings = useMemo(
    () =>
      acceptedFindings.filter((finding) => severity === "ALL" || finding.severity === severity),
    [acceptedFindings, severity],
  );
  const highRiskCount = acceptedFindings.filter((finding) => finding.severity === "HIGH").length;

  return (
    <div className="report-view">
      <header className="report-header">
        <div className="report-title-group">
          <span className="report-type-icon analysis-icon">
            <ShieldAlert size={21} />
          </span>
          <div>
            <p>{report.document_type}</p>
            <h1>{report.title}</h1>
            <span>{report.file_path}</span>
          </div>
        </div>
        <button type="button" className="secondary-button" onClick={onDownload}>
          <Download size={16} />
          JSON
        </button>
      </header>

      <section className="report-summary">
        <p>{report.summary}</p>
        <div className="metric-grid analysis-metrics">
          <div>
            <span className="metric-icon risk-icon"><AlertTriangle size={17} /></span>
            <strong>{highRiskCount}</strong>
            <small>High risk</small>
          </div>
          <div>
            <span className="metric-icon finding-icon"><ListChecks size={17} /></span>
            <strong>{acceptedFindings.length}</strong>
            <small>Findings</small>
          </div>
          <div>
            <span className="metric-icon clause-icon"><FileText size={17} /></span>
            <strong>{report.clauses.length}</strong>
            <small>Clauses</small>
          </div>
          <div>
            <span className="metric-icon rewrite-icon"><WandSparkles size={17} /></span>
            <strong>{report.rewrites.length}</strong>
            <small>Rewrites</small>
          </div>
        </div>
      </section>

      <nav className="report-tabs" aria-label="Analysis report sections">
        {(["findings", "clauses", "rewrites", "audit"] as AnalysisTab[]).map((item) => (
          <button
            key={item}
            type="button"
            className={tab === item ? "is-active" : ""}
            aria-current={tab === item ? "page" : undefined}
            onClick={() => setTab(item)}
          >
            {humanize(item)}
          </button>
        ))}
      </nav>

      <div className="report-content">
        {tab === "findings" ? (
          <>
            <div className="content-toolbar">
              <h2>Accepted findings</h2>
              <div className="filter-control" aria-label="Filter findings by severity">
                {(["ALL", "HIGH", "MEDIUM", "LOW"] as SeverityFilter[]).map((level) => (
                  <button
                    type="button"
                    key={level}
                    className={severity === level ? "is-active" : ""}
                    onClick={() => setSeverity(level)}
                  >
                    {level === "ALL" ? "All" : humanize(level.toLowerCase())}
                  </button>
                ))}
              </div>
            </div>
            <div className="findings-list">
              {visibleFindings.map((finding) => (
                <FindingCard
                  key={finding.id}
                  finding={finding}
                  expanded={expandedFinding === finding.id}
                  onToggle={() =>
                    setExpandedFinding((current) => (current === finding.id ? null : finding.id))
                  }
                />
              ))}
              {visibleFindings.length === 0 ? <p className="empty-content">No matching findings</p> : null}
            </div>
          </>
        ) : null}

        {tab === "clauses" ? (
          <section>
            <div className="content-toolbar"><h2>Extracted clauses</h2></div>
            <div className="clause-list">
              {report.clauses.map((clause) => (
                <article key={clause.id} className="clause-row">
                  <span className="clause-number">{clause.order}</span>
                  <div>
                    <p>{clause.category || "General"}</p>
                    <h3>{clause.title}</h3>
                    <div className="clause-text">{clause.text}</div>
                    {clause.risk_terms?.length ? (
                      <div className="signal-list">
                        {clause.risk_terms.map((term) => <span key={term}>{term}</span>)}
                      </div>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {tab === "rewrites" ? (
          <section>
            <div className="content-toolbar"><h2>Suggested rewrites</h2></div>
            <div className="rewrite-list">
              {report.rewrites.map((rewrite, index) => (
                <article key={`${rewrite.clause_id}-${index}`} className="rewrite-card">
                  <div className="rewrite-heading">
                    <WandSparkles size={17} />
                    <h3>{report.clauses.find((clause) => clause.id === rewrite.clause_id)?.title ?? rewrite.clause_id}</h3>
                  </div>
                  <div className="rewrite-columns">
                    <div><span>Original</span><p>{rewrite.original_text}</p></div>
                    <div><span>Suggested</span><p>{rewrite.rewritten_text}</p></div>
                  </div>
                  <small>{rewrite.rationale}</small>
                </article>
              ))}
              {report.rewrites.length === 0 ? <p className="empty-content">No rewrites proposed</p> : null}
            </div>
          </section>
        ) : null}

        {tab === "audit" ? (
          <section className="audit-section">
            <div className="content-toolbar"><h2>Analysis record</h2></div>
            <dl className="audit-grid">
              <div><dt>Document ID</dt><dd>{report.document_id}</dd></div>
              <div><dt>Schema</dt><dd>{report.schema_version}</dd></div>
              <div><dt>Evidence records</dt><dd>{report.evidence.length}</dd></div>
              <div><dt>Entities</dt><dd>{report.entities.length}</dd></div>
            </dl>
            {report.entities.length ? (
              <div className="entity-table">
                {report.entities.map((entity, index) => (
                  <div key={`${entity.label}-${entity.text}-${index}`}>
                    <span>{entity.label}</span><strong>{entity.text}</strong><small>{entity.source ?? "heuristic"}</small>
                  </div>
                ))}
              </div>
            ) : null}
            {report.limitations?.length ? (
              <div className="limitations-block">
                <h3><Info size={17} /> Review limitations</h3>
                <ul>{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
            ) : null}
          </section>
        ) : null}
      </div>
    </div>
  );
}
