import { AlertTriangle, ArrowRight, Download, GitCompareArrows } from "lucide-react";
import { useMemo, useState } from "react";

import type { ClauseDeltaStatus, ComparisonReport } from "../api/types";
import { formatScore, humanize } from "../lib/format";

type DeltaFilter = "all" | ClauseDeltaStatus;

interface ComparisonReportViewProps {
  report: ComparisonReport;
  onDownload: () => void;
}

export function ComparisonReportView({ report, onDownload }: ComparisonReportViewProps) {
  const [filter, setFilter] = useState<DeltaFilter>("all");
  const visibleDeltas = useMemo(
    () => report.clause_deltas.filter((delta) => filter === "all" || delta.status === filter),
    [filter, report.clause_deltas],
  );

  return (
    <div className="report-view comparison-view">
      <header className="report-header">
        <div className="report-title-group">
          <span className="report-type-icon compare-icon"><GitCompareArrows size={21} /></span>
          <div>
            <p>Version comparison</p>
            <h1>{report.original_type || "Contract"}</h1>
            <span className="comparison-document-pair">
              {report.original_document} <ArrowRight size={12} /> {report.modified_document}
            </span>
          </div>
        </div>
        <button type="button" className="secondary-button" onClick={onDownload}>
          <Download size={16} />
          JSON
        </button>
      </header>

      <section className="report-summary">
        <div className="metric-grid comparison-metrics">
          <div><strong>{report.summary.matched}</strong><small>Matched</small></div>
          <div><strong>{report.summary.changed}</strong><small>Changed</small></div>
          <div><strong>{report.summary.added}</strong><small>Added</small></div>
          <div><strong>{report.summary.removed}</strong><small>Removed</small></div>
          <div><strong>{report.risk_signals.length}</strong><small>Risk signals</small></div>
        </div>
      </section>

      {report.risk_signals.length ? (
        <section className="comparison-risks" aria-labelledby="risk-signals-heading">
          <div className="content-toolbar"><h2 id="risk-signals-heading">Risk signals</h2></div>
          <div className="risk-signal-list">
            {report.risk_signals.map((signal, index) => (
              <article key={`${signal.type}-${signal.clause}-${index}`}>
                <span className={`severity-badge severity-${signal.severity.toLowerCase()}`}>{signal.severity}</span>
                <AlertTriangle size={17} />
                <div><strong>{humanize(signal.type)}</strong><p>{signal.detail}</p><small>{signal.clause}</small></div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className="comparison-deltas" aria-labelledby="clause-changes-heading">
        <div className="content-toolbar">
          <h2 id="clause-changes-heading">Clause changes</h2>
          <div className="filter-control" aria-label="Filter clause changes">
            {(["all", "changed", "added", "removed", "unchanged"] as DeltaFilter[]).map((status) => (
              <button
                type="button"
                key={status}
                className={filter === status ? "is-active" : ""}
                onClick={() => setFilter(status)}
              >
                {humanize(status)}
              </button>
            ))}
          </div>
        </div>
        <div className="delta-list">
          {visibleDeltas.map((delta, index) => (
            <article className={`delta-row delta-${delta.status}`} key={`${delta.original_clause_id}-${delta.modified_clause_id}-${index}`}>
              <div className="delta-heading">
                <span className={`delta-status status-${delta.status}`}>{humanize(delta.status)}</span>
                <strong>{delta.modified_title ?? delta.original_title ?? "Untitled clause"}</strong>
                <small>{formatScore(delta.similarity)} similarity</small>
              </div>
              <div className="delta-columns">
                <div>
                  <span>Original</span>
                  <p>{delta.original_preview || "Not present"}</p>
                  {delta.original_risk_terms?.length ? <small>Risk terms: {delta.original_risk_terms.join(", ")}</small> : null}
                </div>
                <div>
                  <span>Modified</span>
                  <p>{delta.modified_preview || "Not present"}</p>
                  {delta.modified_risk_terms?.length ? <small>Risk terms: {delta.modified_risk_terms.join(", ")}</small> : null}
                </div>
              </div>
            </article>
          ))}
          {visibleDeltas.length === 0 ? <p className="empty-content">No matching clause changes</p> : null}
        </div>
      </section>

      {report.notes?.length ? (
        <section className="comparison-notes">
          <h2>Review notes</h2>
          <ul>{report.notes.map((note) => <li key={note}>{note}</li>)}</ul>
        </section>
      ) : null}
    </div>
  );
}
