import { apiRequest } from "@/lib/api-client";

export type AnalysisStatus = "queued" | "running" | "succeeded" | "failed";
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
  input_manifest: { page_count?: number; page_ids?: number[] };
  result_summary: MachineAnalysisResult;
  usage_metadata: { input_tokens?: number; output_tokens?: number; total_tokens?: number; request_count?: number; vision_page_count?: number };
  task_counts: Record<"total" | AnalysisStatus, number>;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  failure_code: string;
  safe_failure_message: string;
  created_at: string;
  updated_at: string;
};

export type FindingDecision = "accepted" | "edited_accepted" | "rejected" | "needs_clarification";
export type FindingSource = {
  id: number; document_revision: number; document_page: number; document_title: string;
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
  sources: FindingSource[]; reviews: FindingReview[]; created_at: string;
};
export type IntelligenceConflict = {
  id: number; analysis_run: number; semantic_key: string; participant_key: string;
  version: number; conflict_type: string; explanation: string;
  status: "open" | "resolved" | "dismissed"; findings: ExtractedFinding[];
  resolved_by: string | null; resolution_note: string; resolved_at: string | null;
  supersedes: number | null; created_at: string;
};

function projectPath(slug: string, projectId: string | number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${encodeURIComponent(String(projectId))}`;
}

export const analysisApi = {
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
};
