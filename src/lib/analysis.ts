import { apiRequest } from "@/lib/api-client";

export type AnalysisStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type EvidenceReference = {
  document_page_id: number;
  page_number: number;
  drawing_sheet_id: number | null;
  sheet_number: string;
  evidence_excerpt: string;
  visual_evidence_description: string;
};
export type MachineCandidate = {
  category: string;
  subject: string;
  value: string;
  support: "explicit" | "strongly_supported" | "inferred" | "uncertain";
  evidence: EvidenceReference[];
};
export type MachineAnalysisResult = {
  document_type_candidate?: string;
  document_summary?: string;
  candidates?: MachineCandidate[];
  unresolved_questions?: string[];
};
export type AnalysisRun = {
  id: number;
  run_kind: "document" | "project_set";
  document_revision: number;
  document: number;
  requested_by: string;
  predecessor: number | null;
  status: AnalysisStatus;
  provider: string;
  model: string;
  prompt_version: string;
  schema_version: string;
  analysis_version: string;
  input_manifest: {
    project_id?: number;
    document_revision_id?: number;
    document_revision_ids?: number[];
    page_count?: number;
    page_ids?: number[];
    documents?: Array<{
      document_id: number;
      document_revision_id: number;
      title: string;
      category: string;
      discipline: string;
      source_priority: string;
      page_ids: number[];
    }>;
  };
  result_summary: MachineAnalysisResult;
  usage_metadata: {
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
    request_count?: number;
    vision_page_count?: number;
    reconciliation?: { finding_trades?: Record<string, string> };
  };
  task_counts: Record<"total" | AnalysisStatus, number>;
  progress: { completed: number; total: number; active: number; queued: number; failed: number; cancelled: number; active_pages: number[]; synthesis: AnalysisStatus | "not_created" };
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  failure_code: string;
  safe_failure_message: string;
  created_at: string;
  updated_at: string;
};

export type FindingDecision = "accepted" | "edited_accepted" | "rejected" | "needs_clarification";
export type FindingHandlingStatus =
  | "ai_handled"
  | "needs_attention"
  | "conflicting"
  | "human_confirmed"
  | "human_edited"
  | "human_rejected"
  | "human_needs_follow_up";
export type FindingSource = {
  id: number; document: number; document_revision: number; document_page: number; document_title: string;
  revision_label: string; page_number: number; drawing_sheet: number | null;
  sheet_number: string; sheet_title: string; analysis_task_run: number;
  relation: string; evidence_mode: string; evidence_excerpt: string;
  visual_evidence_description: string; created_at: string;
};
export type FindingReview = {
  id: number; finding: number; reviewer: string; decision: FindingDecision;
  reviewed_value: string; review_note: string; supersedes: number | null; created_at: string;
};
export type ExtractedFinding = {
  id: number; analysis_run: number; analysis_task_run: number; document_revision: number;
  source_candidate_key: string; semantic_key: string; category: string; subject: string;
  machine_value: string; machine_support: string; schema_version: string;
  review_status: "unreviewed" | FindingDecision; effective_value: string;
  handling_status: FindingHandlingStatus;
  sources: FindingSource[]; reviews: FindingReview[]; created_at: string;
};
export type IntelligenceConflict = {
  id: number; analysis_run: number; semantic_key: string; participant_key: string;
  version: number; conflict_type: string; explanation: string;
  status: "open" | "resolved" | "dismissed"; findings: ExtractedFinding[];
  resolved_by: string | null; resolution_note: string; resolved_at: string | null;
  supersedes: number | null; created_at: string;
};
export type ProjectReviewState = {
  current_run: AnalysisRun | null;
  counts: ProjectReviewCounts;
  trade_counts: Record<string, ProjectReviewFilterCounts>;
  open_conflict_group_count: number;
  materialized: boolean;
};
export type ProjectReviewFilterKey = "all" | "ai_handled" | "needs_attention" | "conflicts" | "reviewed_by_you";
export type ProjectReviewFilterCounts = Record<ProjectReviewFilterKey, number>;
export type ProjectReviewCounts = {
  total: number; reviewed: number; confirmed: number; not_relevant: number;
  follow_up: number; unreviewed: number; ai_handled: number; conflicting: number;
  reviewed_by_human: number; needs_attention: number; complete: boolean;
};
export type ProjectReviewFindingPage = {
  count: number; page: number; page_size: number; results: ExtractedFinding[];
};
export type IntelligenceBlocker = { code: string; message: string; count: number };
export type IntelligenceCandidateRun = {
  id: number; run_kind: "document" | "project_set";
  document_id: number; document_title: string; document_revision_id: number;
  revision_label: string; is_current_revision: boolean; finding_count: number;
  unreviewed_count: number; needs_clarification_count: number; created_at: string;
  document_count: number; page_count: number; covered_document_revision_ids: number[];
};
export type IntelligenceReadiness = {
  eligible: boolean; blockers: IntelligenceBlocker[]; fingerprint: string;
  summary_counts: Record<string, number>;
};
export type SnapshotProvenance = {
  id: number; finding_source: number; document_revision: number; document_page: number;
  page_number: number; drawing_sheet: number | null; sheet_number: string; sheet_title: string;
  analysis_task_run: number; evidence_excerpt: string; visual_evidence_description: string;
};
export type SnapshotEntry = {
  id: number; finding: number; finding_review: number | null; decision: FindingDecision | "machine_handled";
  effective_value: string; semantic_key: string; category: string; subject: string;
  machine_value: string; included_in_intelligence: boolean; provenance: SnapshotProvenance[];
};
export type SnapshotSource = {
  id: number; analysis_run: number; document: number; document_title: string;
  document_revision: number; revision_label: string; document_is_active: boolean; entries: SnapshotEntry[];
};
export type IntelligenceApproval = {
  id: number; project: number; snapshot: number; approver: string; approved_at: string;
  approval_note: string; readiness_result: Record<string, unknown>;
};
export type IntelligenceSnapshot = {
  id: number; project: number; version: number; fingerprint: string; schema_version: string;
  summary_counts: Record<string, number>; created_by: string; created_at: string;
  sources: SnapshotSource[]; approval: IntelligenceApproval | null; is_stale: boolean;
  approval_blockers?: IntelligenceBlocker[];
};

function projectPath(slug: string, projectId: string | number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${encodeURIComponent(String(projectId))}`;
}

export const analysisApi = {
  projectReviewState(slug: string, projectId: string | number, signal?: AbortSignal) {
    return apiRequest<ProjectReviewState>(`${projectPath(slug, projectId)}/project-review-state/`, {
      signal,
    });
  },
  projectReviewFindings(
    slug: string,
    projectId: string | number,
    options: { trade: string; filter: ProjectReviewFilterKey; page?: number; pageSize?: number },
    signal?: AbortSignal,
  ) {
    const params = new URLSearchParams({
      trade: options.trade,
      filter: options.filter,
      page: String(options.page ?? 1),
      page_size: String(options.pageSize ?? 25),
    });
    return apiRequest<ProjectReviewFindingPage>(`${projectPath(slug, projectId)}/project-review-findings/?${params}`, { signal });
  },
  projectSetRuns(slug: string, projectId: string | number, signal?: AbortSignal) {
    return apiRequest<AnalysisRun[]>(`${projectPath(slug, projectId)}/project-set-analysis-runs/`, {
      signal,
    });
  },
  requestProjectSetRun(slug: string, projectId: string | number) {
    return apiRequest<AnalysisRun>(`${projectPath(slug, projectId)}/project-set-analysis-runs/`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },
  list(slug: string, projectId: string | number, documentId: number, revisionId: number, signal?: AbortSignal) {
    return apiRequest<AnalysisRun[]>(`${projectPath(slug, projectId)}/documents/${documentId}/revisions/${revisionId}/analysis-runs/`, { signal });
  },
  request(slug: string, projectId: string | number, documentId: number, revisionId: number) {
    return apiRequest<AnalysisRun>(`${projectPath(slug, projectId)}/documents/${documentId}/revisions/${revisionId}/analysis-runs/`, { method: "POST", body: JSON.stringify({}) });
  },
  retrieve(slug: string, projectId: string | number, runId: number, signal?: AbortSignal) {
    return apiRequest<AnalysisRun>(`${projectPath(slug, projectId)}/analysis-runs/${runId}/`, { signal });
  },
  retry(slug: string, projectId: string | number, runId: number) {
    return apiRequest<AnalysisRun>(`${projectPath(slug, projectId)}/analysis-runs/${runId}/retry/`, { method: "POST", body: JSON.stringify({}) });
  },
  cancel(slug: string, projectId: string | number, runId: number) {
    return apiRequest<AnalysisRun>(`${projectPath(slug, projectId)}/analysis-runs/${runId}/cancel/`, { method: "POST", body: JSON.stringify({}) });
  },
  findings(slug: string, projectId: string | number, runId: number, signal?: AbortSignal) {
    return apiRequest<ExtractedFinding[]>(`${projectPath(slug, projectId)}/analysis-runs/${runId}/findings/`, { signal });
  },
  materialize(slug: string, projectId: string | number, runId: number) {
    return apiRequest<ExtractedFinding[]>(`${projectPath(slug, projectId)}/analysis-runs/${runId}/findings/materialize/`, { method: "POST", body: JSON.stringify({}) });
  },
  review(slug: string, projectId: string | number, findingId: number, payload: { decision: FindingDecision; reviewed_value?: string; review_note?: string }) {
    return apiRequest<FindingReview>(`${projectPath(slug, projectId)}/findings/${findingId}/reviews/`, { method: "POST", body: JSON.stringify(payload) });
  },
  conflicts(slug: string, projectId: string | number, signal?: AbortSignal) {
    return apiRequest<IntelligenceConflict[]>(`${projectPath(slug, projectId)}/conflicts/`, { signal });
  },
  resolveConflict(slug: string, projectId: string | number, conflictId: number, payload: { status: "resolved" | "dismissed"; resolution_note?: string }) {
    return apiRequest<IntelligenceConflict>(`${projectPath(slug, projectId)}/conflicts/${conflictId}/resolve/`, { method: "POST", body: JSON.stringify(payload) });
  },
  intelligenceCandidates(slug: string, projectId: string | number, signal?: AbortSignal) {
    return apiRequest<{ candidate_runs: IntelligenceCandidateRun[] }>(`${projectPath(slug, projectId)}/intelligence-readiness/`, { signal });
  },
  intelligenceReadiness(slug: string, projectId: string | number, analysisRunIds: number[], signal?: AbortSignal) {
    return apiRequest<IntelligenceReadiness>(`${projectPath(slug, projectId)}/intelligence-readiness/`, { method: "POST", body: JSON.stringify({ analysis_run_ids: analysisRunIds }), signal });
  },
  snapshots(slug: string, projectId: string | number, signal?: AbortSignal) {
    return apiRequest<IntelligenceSnapshot[]>(`${projectPath(slug, projectId)}/intelligence-snapshots/`, { signal });
  },
  createSnapshot(slug: string, projectId: string | number, analysisRunIds: number[]) {
    return apiRequest<IntelligenceSnapshot>(`${projectPath(slug, projectId)}/intelligence-snapshots/`, { method: "POST", body: JSON.stringify({ analysis_run_ids: analysisRunIds }) });
  },
  approveSnapshot(slug: string, projectId: string | number, snapshotId: number, approvalNote = "") {
    return apiRequest<IntelligenceApproval>(`${projectPath(slug, projectId)}/intelligence-snapshots/${snapshotId}/approval/`, { method: "POST", body: JSON.stringify({ approval_note: approvalNote }) });
  },
};
