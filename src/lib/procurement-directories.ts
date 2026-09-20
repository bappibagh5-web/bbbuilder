import { apiRequest } from "@/lib/api-client";

type Page<T, S, F> = { count: number; next: string | null; previous: string | null; page: number; page_size: number; results: T[]; summary: S; filters: F };
export type CampaignDirectoryItem = { id: number; project_id: number; project_number: string; project_name: string; trade_key: string; trade: string; scope_version_id: number; status: string; recipient_count: number; invited_count: number; delivered_count: number; responded_count: number; qualified_count: number; not_reviewed_count: number; bid_count: number; created_at: string; project_url: string };
export type CampaignDirectoryResponse = Page<CampaignDirectoryItem, { total: number; draft: number; prepared: number; closed: number }, { trades: { trade_key: string; trade_category: string }[]; statuses: { value: string; label: string }[] }>;
export type ComparisonDirectoryItem = { id: number; project_id: number; project_number: string; project_name: string; trade_key: string; trade: string; scope_version_id: number; status: string; bidder_count: number; human_review_id: number | null; human_review_version: number | null; human_review_status: string; selected_for_proposal: boolean; created_at: string; project_url: string };
export type ComparisonDirectoryResponse = Page<ComparisonDirectoryItem, { total: number; draft: number; ready: number; selected_for_proposal: number }, { trades: { scope_package__trade_key: string; scope_package__trade_category: string }[]; statuses: { value: string; label: string }[] }>;
export type ProposalDirectoryItem = { id: number; project_id: number; project_number: string; project_name: string; client_name: string; proposal_number: string; version_id: number | null; version: number | null; status: string; estimate_version_id: number | null; estimate_version: number | null; currency: string | null; proposed_amount: string | null; pdf_available: boolean; award_status: string; issue_date: string | null; project_url: string };
export type ProposalDirectoryResponse = Page<ProposalDirectoryItem, { total: number; draft: number; finalized: number; awarded: number }, { statuses: { value: string; label: string }[]; award_statuses: { value: string; label: string }[] }>;

function path(slug: string, resource: string, query: URLSearchParams) { const suffix = query.toString(); return `/organizations/${encodeURIComponent(slug)}/${resource}/${suffix ? `?${suffix}` : ""}`; }
export const procurementDirectoriesApi = {
  campaigns(slug: string, query: URLSearchParams, signal?: AbortSignal) { return apiRequest<CampaignDirectoryResponse>(path(slug, "procurement-campaigns", query), { signal }); },
  comparisons(slug: string, query: URLSearchParams, signal?: AbortSignal) { return apiRequest<ComparisonDirectoryResponse>(path(slug, "procurement-comparisons", query), { signal }); },
  proposals(slug: string, query: URLSearchParams, signal?: AbortSignal) { return apiRequest<ProposalDirectoryResponse>(path(slug, "client-proposals", query), { signal }); },
};
