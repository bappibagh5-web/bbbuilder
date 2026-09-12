import { apiRequest } from "@/lib/api-client";

export type ContractorCompany = { id: number; display_name: string; website: string; phone: string; email: string; address: string; city: string; province: string; country: string; source_type: "internal" | "discovered"; external_provider: string; latitude: string | null; longitude: string | null; is_active: boolean };
export type ContractorCandidate = { id: number; scope_package: number; scope_version: number; status: "candidate" | "shortlisted" | "approved_for_outreach" | "rejected"; company: ContractorCompany; match_score: number; match_reasons: string[]; google_rating: number | null; google_review_count: number | null; distance_miles: number | null; created_at: string; updated_at: string };
export type TradeCoverage = { scope_package: number; scope_version: number; trade_key: string; trade_category: string; title: string; candidates_found: number; shortlisted_count: number; coverage_status: "ready" | "needs_more_candidates" };
export type TradeCoverageResponse = { minimum_shortlist_target: number; trades: TradeCoverage[] };
export type ContractorContact = { id: number; name: string; title: string; email: string; phone: string; is_primary: boolean; is_active: boolean; created_at: string; updated_at: string };
export type ContractorContactInput = { name?: string; title?: string; email?: string; phone?: string; is_primary?: boolean; is_active?: boolean };
export type ContractorContactSuggestionSource = { label: "Company website" | "Contact page" | "Team page"; url: string; fields: string[] };
export type ContractorContactSuggestion = Required<ContractorContactInput> & { sources: ContractorContactSuggestionSource[] };
export type ContractorContactEnrichment = { suggestions: ContractorContactSuggestion[]; pages_checked: string[] };
export type ContractorTradeCapability = { id: number; trade_key: string; trade_label: string; keywords: string[]; service_cities: string[]; province: string; is_active: boolean };
export type ContractorCompanyProfile = ContractorCompany & { trade_capabilities: ContractorTradeCapability[]; contacts: ContractorContact[]; contact_ready: boolean; shortlist_statuses: { scope_package: number; trade_category: string; status: ContractorCandidate["status"] }[]; google_rating: number | null; google_review_count: number | null };
function base(slug: string, projectId: number) { return `/organizations/${encodeURIComponent(slug)}/projects/${projectId}`; }
export const contractorsApi = {
  candidates(slug: string, projectId: number, signal?: AbortSignal, scopePackageId?: number) { const query = scopePackageId ? `?scope_package=${scopePackageId}` : ""; return apiRequest<ContractorCandidate[]>(`${base(slug, projectId)}/contractor-candidates/${query}`, { signal }); },
  coverage(slug: string, projectId: number, signal?: AbortSignal) { return apiRequest<TradeCoverageResponse>(`${base(slug, projectId)}/contractor-coverage/`, { signal }); },
  profile(slug: string, projectId: number, companyId: number) { return apiRequest<ContractorCompanyProfile>(`${base(slug, projectId)}/contractor-companies/${companyId}/`); },
  enrichContacts(slug: string, projectId: number, companyId: number) { return apiRequest<ContractorContactEnrichment>(`${base(slug, projectId)}/contractor-companies/${companyId}/contact-enrichment/`, { method: "POST" }); },
  addContact(slug: string, projectId: number, companyId: number, input: ContractorContactInput) { return apiRequest<ContractorContact>(`${base(slug, projectId)}/contractor-companies/${companyId}/contacts/`, { method: "POST", body: JSON.stringify(input) }); },
  updateContact(slug: string, projectId: number, companyId: number, contactId: number, input: ContractorContactInput) { return apiRequest<ContractorContact>(`${base(slug, projectId)}/contractor-companies/${companyId}/contacts/${contactId}/`, { method: "PATCH", body: JSON.stringify(input) }); },
  search(slug: string, projectId: number, input: { scope_package_id: number; keywords: string[] }) { return apiRequest<{ discovery_request_id: number; result_count: number; partial_results: boolean; candidates: ContractorCandidate[] }>(`${base(slug, projectId)}/contractor-discovery/search/`, { method: "POST", body: JSON.stringify(input) }); },
  setStatus(slug: string, projectId: number, candidateId: number, status: ContractorCandidate["status"]) { return apiRequest<ContractorCandidate>(`${base(slug, projectId)}/contractor-candidates/${candidateId}/`, { method: "PATCH", body: JSON.stringify({ status }) }); },
};
