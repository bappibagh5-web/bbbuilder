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
};
