import { FileSearch, GitCompareArrows, RefreshCw, Trash2 } from "lucide-react";

import type { Job } from "../api/types";
import { formatDate, humanize, statusLabel } from "../lib/format";

interface JobHistoryProps {
  jobs: Job[];
  selectedJobId: string | null;
  loading: boolean;
  onRefresh: () => void;
  onSelect: (job: Job) => void;
  onDelete: (job: Job) => void;
}

export function JobHistory({
  jobs,
  selectedJobId,
  loading,
  onRefresh,
  onSelect,
  onDelete,
}: JobHistoryProps) {
  return (
    <section className="history-section" aria-labelledby="history-heading">
      <div className="section-heading-row compact">
        <div>
          <p className="section-kicker">Workspace</p>
          <h2 id="history-heading">Recent reviews</h2>
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label="Refresh recent reviews"
          title="Refresh"
          onClick={onRefresh}
          disabled={loading}
        >
          <RefreshCw size={17} className={loading ? "spin" : ""} />
        </button>
      </div>

      <div className="job-list">
        {jobs.length === 0 ? <p className="empty-list">No reviews yet</p> : null}
        {jobs.map((job) => {
          const fileLabel = job.inputs.map((input) => input.name).join(" / ");
          return (
            <div
              className={`job-row${selectedJobId === job.id ? " is-selected" : ""}`}
              key={job.id}
            >
              <button type="button" className="job-select" onClick={() => onSelect(job)}>
                <span className="job-type-icon" aria-hidden="true">
                  {job.type === "analysis" ? (
                    <FileSearch size={17} />
                  ) : (
                    <GitCompareArrows size={17} />
                  )}
                </span>
                <span className="job-copy">
                  <strong title={fileLabel}>{fileLabel}</strong>
                  <small>
                    {humanize(job.type)} / {formatDate(job.created_at)}
                  </small>
                </span>
                <span className={`status-dot status-${job.status}`} title={statusLabel(job.status)} />
              </button>
              {job.status === "completed" || job.status === "failed" || job.status === "cancelled" ? (
                <button
                  type="button"
                  className="job-delete"
                  aria-label={`Delete ${fileLabel}`}
                  title="Delete review"
                  onClick={() => onDelete(job)}
                >
                  <Trash2 size={15} />
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
