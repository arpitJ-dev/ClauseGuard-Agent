import { GitCompareArrows, ScanSearch } from "lucide-react";
import { FormEvent, useState } from "react";

import type { JobType } from "../api/types";
import { FileDropzone } from "./FileDropzone";

interface SubmissionPanelProps {
  mode: JobType;
  busy: boolean;
  engineReady: boolean;
  onModeChange: (mode: JobType) => void;
  onAnalyze: (file: File) => Promise<void>;
  onCompare: (original: File, modified: File) => Promise<void>;
}

export function SubmissionPanel({
  mode,
  busy,
  engineReady,
  onModeChange,
  onAnalyze,
  onCompare,
}: SubmissionPanelProps) {
  const [document, setDocument] = useState<File | null>(null);
  const [original, setOriginal] = useState<File | null>(null);
  const [modified, setModified] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = engineReady && !busy && (mode === "analysis" ? document : original && modified);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      if (mode === "analysis" && document) {
        await onAnalyze(document);
        setDocument(null);
      } else if (mode === "comparison" && original && modified) {
        await onCompare(original, modified);
        setOriginal(null);
        setModified(null);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The request could not be submitted.");
    }
  };

  return (
    <section className="submission-section" aria-labelledby="new-review-heading">
      <div className="section-heading-row">
        <div>
          <p className="section-kicker">New review</p>
          <h2 id="new-review-heading">Document intake</h2>
        </div>
      </div>

      <div className="segmented-control" aria-label="Review mode">
        <button
          type="button"
          className={mode === "analysis" ? "is-active" : ""}
          aria-pressed={mode === "analysis"}
          onClick={() => onModeChange("analysis")}
        >
          <ScanSearch size={16} />
          Analyze
        </button>
        <button
          type="button"
          className={mode === "comparison" ? "is-active" : ""}
          aria-pressed={mode === "comparison"}
          onClick={() => onModeChange("comparison")}
        >
          <GitCompareArrows size={16} />
          Compare
        </button>
      </div>

      <form onSubmit={(event) => void submit(event)}>
        {mode === "analysis" ? (
          <FileDropzone
            id="analysis-document"
            label="Contract"
            file={document}
            disabled={busy}
            onChange={setDocument}
          />
        ) : (
          <div className="comparison-files">
            <FileDropzone
              id="original-document"
              label="Original"
              file={original}
              disabled={busy}
              onChange={setOriginal}
            />
            <FileDropzone
              id="modified-document"
              label="Modified"
              file={modified}
              disabled={busy}
              onChange={setModified}
            />
          </div>
        )}

        {error ? <div className="inline-alert error-alert">{error}</div> : null}
        {!engineReady ? (
          <div className="inline-alert warning-alert">Analysis engine unavailable</div>
        ) : null}

        <button className="primary-button full-width" type="submit" disabled={!canSubmit}>
          {mode === "analysis" ? <ScanSearch size={17} /> : <GitCompareArrows size={17} />}
          {busy ? "Submitting..." : mode === "analysis" ? "Run analysis" : "Compare versions"}
        </button>
      </form>
    </section>
  );
}
