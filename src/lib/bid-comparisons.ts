import { apiRequest, apiResponse } from "@/lib/api-client";

export type ReadyBidChoice = {
  id: number; company_id: number; company_name: string; revision_label: string;
  revision_sequence: number; submission_id: number; scope_package_id: number;
  scope_version_id: number; scope_version: number; trade: string;
  base_bid: string | null; currency: string; received_at: string;
};
export type ComparisonSummary = {
  id: number; sequence: number; status: "draft" | "ready"; trade: string;
  scope_package_id: number; scope_version_id: number; scope_version: number;
  bidder_count: number; updated_at: string;
};
export type ComparisonAdjustment = {
  id: number; direction: "add" | "deduct"; amount: string; currency: string;
  category: string; description: string; scope_item_id: number | null;
  source_commercial_item_id: number | null;
};
export type ComparisonEntry = {
  id: number; revision_id: number; revision_sequence: number; revision_label: string;
  company_id: number; company_name: string; submission_id: number; received_at: string;
  base_bid: string | null; currency: string; currency_review: string; tax_treatment: string;
  validity_days: number | null; validity_date: string | null; schedule_text: string;
  attachments: { id: number; filename: string }[];
  commercial_items: { id: number; kind: string; title: string; description: string; detail: string; treatment: string; amount: string | null; currency: string; included_in_base: string; scope_item_id: number | null; evidence: { attachment_id: number | null; page_number: number | null; excerpt: string }[] }[];
  unmapped_items: number[];
  coverage: Record<string, { state: string; recorded: boolean; wording: string }>;
  adjustments: ComparisonAdjustment[]; evaluated_amount: string | null; attention_flags: string[];
};
export type ComparisonDetail = ComparisonSummary & {
  notes: string; supersedes_id: number | null; created_by_id: number;
  reviewed_by_id: number | null; created_at: string; reviewed_at: string | null;
  currency_comparable: boolean; comparison_currency: string | null;
  scope_items: { id: number; sequence: number; title: string }[];
  entries: ComparisonEntry[];
};

function base(slug: string, projectId: number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${projectId}/bid-comparisons`;
}

export const bidComparisonsApi = {
  list(slug: string, projectId: number, signal?: AbortSignal) {
    return apiRequest<{ comparisons: ComparisonSummary[]; ready_revisions: ReadyBidChoice[] }>(`${base(slug, projectId)}/`, { signal });
  },
  detail(slug: string, projectId: number, comparisonId: number) {
    return apiRequest<ComparisonDetail>(`${base(slug, projectId)}/${comparisonId}/`);
  },
  create(slug: string, projectId: number, scopeVersionId: number) {
    return apiRequest<ComparisonDetail>(`${base(slug, projectId)}/`, { method: "POST", body: JSON.stringify({ scope_version_id: scopeVersionId }) });
  },
  updateNotes(slug: string, projectId: number, comparisonId: number, notes: string) {
    return apiRequest<ComparisonDetail>(`${base(slug, projectId)}/${comparisonId}/`, { method: "PATCH", body: JSON.stringify({ notes }) });
  },
  addEntry(slug: string, projectId: number, comparisonId: number, revisionId: number) {
    return apiRequest<ComparisonDetail>(`${base(slug, projectId)}/${comparisonId}/entries/`, { method: "POST", body: JSON.stringify({ revision_id: revisionId }) });
  },
  removeEntry(slug: string, projectId: number, comparisonId: number, entryId: number) {
    return apiResponse(`${base(slug, projectId)}/${comparisonId}/entries/${entryId}/`, { method: "DELETE" }).then(() => undefined);
  },
  addAdjustment(slug: string, projectId: number, comparisonId: number, entryId: number, values: Record<string, unknown>) {
    return apiRequest<ComparisonDetail>(`${base(slug, projectId)}/${comparisonId}/entries/${entryId}/adjustments/`, { method: "POST", body: JSON.stringify(values) });
  },
  removeAdjustment(slug: string, projectId: number, comparisonId: number, entryId: number, adjustmentId: number) {
    return apiResponse(`${base(slug, projectId)}/${comparisonId}/entries/${entryId}/adjustments/${adjustmentId}/`, { method: "DELETE" }).then(() => undefined);
  },
  ready(slug: string, projectId: number, comparisonId: number) {
    return apiRequest<ComparisonDetail>(`${base(slug, projectId)}/${comparisonId}/ready/`, { method: "POST", body: "{}" });
  },
};
