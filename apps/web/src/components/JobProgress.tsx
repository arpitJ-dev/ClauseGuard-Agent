import { Radio, Square } from "lucide-react";

import type { Job } from "../api/types";
import { clampProgress, humanize, statusLabel } from "../lib/format";

interface JobProgressProps {
  job: Job;
  connected: boolean;
  onCancel: () => void;
}

export function JobProgress({ job, connected, onCancel }: JobProgressProps) {
  const progress = clampProgress(job.progress);

  return (
    <section className="progress-panel" aria-live="polite">
      <div className="progress-header">
        <div>
          <span className="progress-status">
            <span className={`status-dot status-${job.status}`} />
            {statusLabel(job.status)}
          </span>
          <h2>{humanize(job.stage)}</h2>
        </div>
        <span className={`stream-status${connected ? " is-connected" : ""}`}>
          <Radio size={14} />
          {connected ? "Live" : "Syncing"}
        </span>
      </div>
      <p>{job.message}</p>
      <div className="progress-track" aria-label={`${progress}% complete`}>
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="progress-footer">
        <strong>{progress}%</strong>
        <button type="button" className="secondary-button danger-text" onClick={onCancel}>
          <Square size={14} />
          Cancel
        </button>
      </div>
    </section>
  );
}
