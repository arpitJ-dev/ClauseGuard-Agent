export type JobType = "analysis" | "comparison";
export type JobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "timed_out";
export type Severity = "LOW" | "MEDIUM" | "HIGH";

export interface InputFile {
  name: string;
}

export interface JobError {
  code: string;
  message: string;
}

export interface Job {
  id: string;
  type: JobType;
  status: JobStatus;
  stage: string;
  progress: number;
  message: string;
  inputs: InputFile[];
  report_url?: string;
  error?: JobError;
  exit_code?: number;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface SubmissionResponse {
  job: Job;
  links: {
    self: string;
    events: string;
  };
}

export interface DeleteResponse {
  job: Job;
  deleted: boolean;
}

export interface ModelRole {
  role?: string;
  model?: string;
  provider?: string;
  purpose?: string;
  free_tier_only?: boolean;
  [key: string]: unknown;
}

export interface HealthResponse {
  status: "ok" | "unavailable";
  engine: {
    ready: boolean;
    models?: ModelRole[];
    error?: string;
  };
}

export interface Clause {
  id: string;
  order: number;
  title: string;
  text: string;
  category?: string;
  risk_terms?: string[];
}

export interface Evidence {
  id: string;
  source: string;
  title: string;
  text: string;
  relevance: number;
  clause_id?: string | null;
}

export interface ComponentScores {
  deterministic_rules: number;
  rag_evidence: number;
  primary_reasoning: number;
  verifier_agreement: number;
  clause_structure: number;
  final: number;
  weights: Record<string, number>;
}

export interface Finding {
  id: string;
  issue_type: string;
  severity: Severity;
  clause_id?: string | null;
  clause_title?: string | null;
  explanation: string;
  rule_id?: string;
  signals?: string[];
  evidence?: Evidence[];
  component_scores: ComponentScores;
  accepted: boolean;
  acceptance_threshold?: number;
  model_confidence: number;
  verifier_confidence: number;
  verifier_status?: "verified" | "not_run" | "unavailable";
  verifier_rationale?: string;
  suggested_rewrite?: string | null;
}

export interface LegalEntity {
  text: string;
  label: string;
  source?: string;
}

export interface Rewrite {
  clause_id: string;
  original_text: string;
  rewritten_text: string;
  rationale: string;
}

export interface AnalysisReport {
  schema_version: "1.0";
  document_id: string;
  file_path: string;
  title: string;
  document_type: string;
  summary: string;
  clauses: Clause[];
  entities: LegalEntity[];
  evidence: Evidence[];
  findings: Finding[];
  rewrites: Rewrite[];
  generated_at?: string;
  limitations?: string[];
}

export type ClauseDeltaStatus = "unchanged" | "changed" | "added" | "removed";

export interface ClauseDelta {
  status: ClauseDeltaStatus;
  similarity: number;
  original_clause_id?: string | null;
  original_title?: string | null;
  original_category?: string | null;
  original_preview?: string;
  original_risk_terms?: string[];
  modified_clause_id?: string | null;
  modified_title?: string | null;
  modified_category?: string | null;
  modified_preview?: string;
  modified_risk_terms?: string[];
}

export interface ComparisonRiskSignal {
  type: string;
  clause: string;
  detail: string;
  severity: Severity;
}

export interface ComparisonReport {
  schema_version: "1.0";
  comparison_id: string;
  original_document: string;
  modified_document: string;
  original_type: string;
  modified_type: string;
  original_clause_count: number;
  modified_clause_count: number;
  summary: {
    matched: number;
    changed: number;
    added: number;
    removed: number;
  };
  clause_deltas: ClauseDelta[];
  risk_signals: ComparisonRiskSignal[];
  notes?: string[];
}

export type Report = AnalysisReport | ComparisonReport;

export function isAnalysisReport(report: Report): report is AnalysisReport {
  return "document_id" in report;
}

export function isTerminalStatus(status: JobStatus): boolean {
  return ["completed", "failed", "cancelled", "timed_out"].includes(status);
}
