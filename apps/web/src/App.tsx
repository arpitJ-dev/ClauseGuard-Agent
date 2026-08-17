import {
  AlertCircle,
  Menu,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  deleteJob,
  getHealth,
  getReport,
  listJobs,
  submitAnalysis,
  submitComparison,
} from "./api/client";
import type { HealthResponse, Job, JobType, Report } from "./api/types";
import { isAnalysisReport, isTerminalStatus } from "./api/types";
import { AnalysisReportView } from "./components/AnalysisReportView";
import { ComparisonReportView } from "./components/ComparisonReportView";
import { JobHistory } from "./components/JobHistory";
import { JobProgress } from "./components/JobProgress";
import { SubmissionPanel } from "./components/SubmissionPanel";
import { useJobStream } from "./hooks/useJobStream";

function errorMessage(cause: unknown): string {
  if (cause instanceof ApiError && cause.retryAfter) {
    return `${cause.message} Retry in ${cause.retryAfter} seconds.`;
  }
  return cause instanceof Error ? cause.message : "An unexpected error occurred.";
}

function upsertJob(jobs: Job[], job: Job): Job[] {
  const remaining = jobs.filter((candidate) => candidate.id !== job.id);
  return [job, ...remaining].sort(
    (left, right) => Date.parse(right.created_at) - Date.parse(left.created_at),
  );
}

export default function App() {
  const [mode, setMode] = useState<JobType>("analysis");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [streamConnected, setStreamConnected] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<Job | null>(null);

  const engineReady = health?.status === "ok" && health.engine.ready;
  const selectedIsActive = Boolean(selectedJob && !isTerminalStatus(selectedJob.status));

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await getHealth());
    } catch {
      setHealth({ status: "unavailable", engine: { ready: false } });
    }
  }, []);

  const refreshJobs = useCallback(async () => {
    setLoadingJobs(true);
    try {
      const nextJobs = await listJobs();
      setJobs(nextJobs);
      setSelectedJob((current) =>
        current ? (nextJobs.find((job) => job.id === current.id) ?? current) : current,
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  const loadReport = useCallback(async (job: Job) => {
    if (job.status !== "completed") return;
    setLoadingReport(true);
    try {
      setReport(await getReport(job.id));
    } catch (cause) {
      setError(errorMessage(cause));
      setReport(null);
    } finally {
      setLoadingReport(false);
    }
  }, []);

  useEffect(() => {
    const initialTimer = window.setTimeout(() => {
      void refreshHealth();
      void refreshJobs();
    }, 0);
    const healthTimer = window.setInterval(() => void refreshHealth(), 30000);
    const jobsTimer = window.setInterval(() => void refreshJobs(), 15000);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(healthTimer);
      window.clearInterval(jobsTimer);
    };
  }, [refreshHealth, refreshJobs]);

  const handleJobUpdate = useCallback(
    (job: Job) => {
      setJobs((current) => upsertJob(current, job));
      setSelectedJob((current) => (current?.id === job.id ? job : current));
      if (job.status === "completed") void loadReport(job);
      if (job.error) setError(job.error.message);
    },
    [loadReport],
  );

  const handleConnectionChange = useCallback((connected: boolean) => {
    setStreamConnected(connected);
  }, []);

  useJobStream({
    jobId: selectedJob?.id ?? null,
    active: selectedIsActive,
    onJob: handleJobUpdate,
    onConnectionChange: handleConnectionChange,
  });

  const selectJob = useCallback(
    (job: Job) => {
      setSelectedJob(job);
      setReport(null);
      setError(job.error?.message ?? null);
      setSidebarOpen(false);
      if (job.status === "completed") void loadReport(job);
    },
    [loadReport],
  );

  const acceptSubmission = (job: Job) => {
    setJobs((current) => upsertJob(current, job));
    setSelectedJob(job);
    setReport(null);
    setError(null);
    setSidebarOpen(false);
  };

  const analyze = async (file: File) => {
    setSubmitting(true);
    try {
      acceptSubmission((await submitAnalysis(file)).job);
    } finally {
      setSubmitting(false);
    }
  };

  const compare = async (original: File, modified: File) => {
    setSubmitting(true);
    try {
      acceptSubmission((await submitComparison(original, modified)).job);
    } finally {
      setSubmitting(false);
    }
  };

  const cancelSelectedJob = async () => {
    if (!selectedJob) return;
    try {
      handleJobUpdate((await deleteJob(selectedJob.id)).job);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };

  const confirmDelete = async () => {
    if (!deleteCandidate) return;
    try {
      const result = await deleteJob(deleteCandidate.id);
      if (result.deleted) {
        setJobs((current) => current.filter((job) => job.id !== deleteCandidate.id));
        if (selectedJob?.id === deleteCandidate.id) {
          setSelectedJob(null);
          setReport(null);
        }
      }
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setDeleteCandidate(null);
    }
  };

  const downloadReport = () => {
    if (!report || !selectedJob) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${selectedJob.type}-${selectedJob.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const activeModelCount = health?.engine.models?.length ?? 0;
  const workspaceState = useMemo(() => {
    if (!selectedJob) return "empty";
    if (selectedIsActive) return "active";
    if (selectedJob.status === "completed") return "complete";
    return "failed";
  }, [selectedIsActive, selectedJob]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-group">
          <button
            type="button"
            className="mobile-menu-button"
            aria-label="Toggle workspace panel"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen((current) => !current)}
          >
            <Menu size={20} />
          </button>
          <span className="brand-mark"><ShieldCheck size={23} /></span>
          <div><strong>ClauseGuard Agent</strong><small>Contract review</small></div>
        </div>
        <button className="engine-health" type="button" onClick={() => void refreshHealth()}>
          <span className={engineReady ? "health-ready" : "health-down"} />
          <span><strong>{engineReady ? "Engine ready" : "Engine unavailable"}</strong><small>{activeModelCount} model roles</small></span>
          <RefreshCw size={15} />
        </button>
      </header>

      <div className="app-layout">
        <aside className={`sidebar${sidebarOpen ? " is-open" : ""}`}>
          <SubmissionPanel
            mode={mode}
            busy={submitting}
            engineReady={engineReady}
            onModeChange={setMode}
            onAnalyze={analyze}
            onCompare={compare}
          />
          <JobHistory
            jobs={jobs}
            selectedJobId={selectedJob?.id ?? null}
            loading={loadingJobs}
            onRefresh={() => void refreshJobs()}
            onSelect={selectJob}
            onDelete={setDeleteCandidate}
          />
        </aside>
        {sidebarOpen ? <button className="sidebar-scrim" aria-label="Close workspace panel" onClick={() => setSidebarOpen(false)} /> : null}

        <main className="workspace">
          {error ? (
            <div className="global-alert" role="alert">
              <AlertCircle size={18} />
              <span>{error}</span>
              <button type="button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={17} /></button>
            </div>
          ) : null}

          {workspaceState === "empty" ? (
            <section className="workspace-empty">
              <span><ShieldCheck size={31} /></span>
              <h1>Review workspace</h1>
              <p>No report selected</p>
            </section>
          ) : null}

          {workspaceState === "active" && selectedJob ? (
            <JobProgress job={selectedJob} connected={streamConnected} onCancel={() => void cancelSelectedJob()} />
          ) : null}

          {workspaceState === "failed" && selectedJob ? (
            <section className="workspace-empty error-state">
              <span><AlertCircle size={31} /></span>
              <h1>{selectedJob.status === "cancelled" ? "Review cancelled" : "Review did not complete"}</h1>
              <p>{selectedJob.error?.message ?? selectedJob.message}</p>
            </section>
          ) : null}

          {workspaceState === "complete" && loadingReport ? (
            <section className="workspace-empty loading-state">
              <span className="spinner" />
              <h1>Loading report</h1>
            </section>
          ) : null}

          {workspaceState === "complete" && report ? (
            isAnalysisReport(report) ? (
              <AnalysisReportView
                key={report.document_id}
                report={report}
                onDownload={downloadReport}
              />
            ) : (
              <ComparisonReportView
                key={report.comparison_id}
                report={report}
                onDownload={downloadReport}
              />
            )
          ) : null}
        </main>
      </div>

      {deleteCandidate ? (
        <div className="modal-backdrop" role="presentation">
          <section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-title">
            <h2 id="delete-title">Delete review?</h2>
            <p>{deleteCandidate.inputs.map((input) => input.name).join(" / ")}</p>
            <div>
              <button type="button" className="secondary-button" onClick={() => setDeleteCandidate(null)}>Cancel</button>
              <button type="button" className="danger-button" onClick={() => void confirmDelete()}>Delete</button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
