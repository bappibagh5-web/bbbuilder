import { apiRequest } from "@/lib/api-client";

export type ContractorCompany = { id: number; display_name: string; website: string; phone: string; email: string; city: string; province: string; source_type: "internal" | "discovered"; is_active: boolean };
export type ContractorCandidate = { id: number; scope_package: number; status: "candidate" | "shortlisted" | "approved_for_outreach" | "rejected"; company: ContractorCompany; created_at: string; updated_at: string };
function base(slug: string, projectId: number) { return `/organizations/${encodeURIComponent(slug)}/projects/${projectId}`; }
export const contractorsApi = {
  candidates(slug: string, projectId: number, signal?: AbortSignal) { return apiRequest<ContractorCandidate[]>(`${base(slug, projectId)}/contractor-candidates/`, { signal }); },
  search(slug: string, projectId: number, input: { scope_package_id: number; city: string; province: string; radius_km?: number; keywords: string[] }) { return apiRequest<{ discovery_request_id: number; result_count: number; candidates: ContractorCandidate[] }>(`${base(slug, projectId)}/contractor-discovery/search/`, { method: "POST", body: JSON.stringify(input) }); },
  setStatus(slug: string, projectId: number, candidateId: number, status: ContractorCandidate["status"]) { return apiRequest<ContractorCandidate>(`${base(slug, projectId)}/contractor-candidates/${candidateId}/`, { method: "PATCH", body: JSON.stringify({ status }) }); },
};
