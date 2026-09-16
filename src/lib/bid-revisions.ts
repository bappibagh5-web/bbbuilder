import { apiRequest } from "@/lib/api-client";

export type BidCommercialItem = {
  id: number; sequence: number; kind: "alternate" | "allowance" | "fee" | "exclusion" | "condition";
  contractor_label: string; title: string; description: string; category: string;
  treatment: string; amount: string | null; currency: string;
  included_in_base: "yes" | "no" | "unclear";
  scope_item_id: number | null; estimator_note: string;
};
export type BidCoverage = {
  id: number; scope_item_id: number; state: string; wording: string;
  estimator_note: string; reviewed: boolean;
};
export type BidEvidence = {
  id: number; attachment_id: number | null; commercial_item_id: number | null;
  coverage_id: number | null; field_key: string; source: string;
  page_number: number | null; excerpt: string; note: string;
};
export type BidRevision = {
  id: number; sequence: number; contractor_label: string;
  status: "draft" | "ready" | "superseded";
  supersedes_id: number | null; superseded_by_ids: number[];
  submission_id: number; scope_version_id: number;
  currency: string; currency_review: "unreviewed" | "confirmed" | "not_stated";
  base_bid: string | null; base_bid_review: "unreviewed" | "confirmed" | "not_stated";
  tax_treatment: "included" | "extra" | "exempt" | "not_stated";
  tax_reviewed: boolean; commercial_items_reviewed: boolean; scope_reviewed: boolean;
  validity_date: string | null; validity_days: number | null;
  schedule_text: string; estimator_notes: string; created_at: string;
  reviewed_at: string | null; reviewed_by_id: number | null;
  readiness_blockers: string[]; commercial_items: BidCommercialItem[];
  scope_coverage: BidCoverage[]; evidence: BidEvidence[];
};
export type BidScopeItemChoice = { id: number; title: string; sequence: number };
export type BidCandidate = {
  kind: string; title: string; description: string; amount: string | null;
  currency: string | null; treatment: string | null; scope_item_id: number | null;
  included_in_base_bid: boolean | null;
  page_number: number; excerpt: string;
};
export type BidExtraction = {
  id: number; attachment_id: number; status: "queued" | "running" | "succeeded" | "failed";
  provider: string; model: string; schema_version: number; candidate_count: number;
  candidates: BidCandidate[]; usage: Record<string, unknown>;
  decisions: { id: number; candidate_index: number; revision_id: number; decision: string }[];
  safe_error_code: string; safe_error_message: string;
};

function base(slug: string, projectId: number, submissionId: number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${projectId}/bid-submissions/${submissionId}`;
}
function revisionBase(slug: string, projectId: number, submissionId: number, revisionId: number) {
  return `${base(slug, projectId, submissionId)}/revisions/${revisionId}`;
}

export const bidRevisionsApi = {
  list(slug: string, projectId: number, submissionId: number) {
    return apiRequest<{ revisions: BidRevision[]; scope_items: BidScopeItemChoice[] }>(
      `${base(slug, projectId, submissionId)}/revisions/`);
  },
  create(slug: string, projectId: number, submissionId: number, label: string, requestKey: string, supersedesId?: number) {
    return apiRequest<BidRevision>(`${base(slug, projectId, submissionId)}/revisions/`, {
      method: "POST", body: JSON.stringify({ contractor_label: label, request_key: requestKey, supersedes_id: supersedesId }),
    });
  },
  update(slug: string, projectId: number, submissionId: number, revisionId: number, values: Record<string, unknown>) {
    return apiRequest<BidRevision>(`${revisionBase(slug, projectId, submissionId, revisionId)}/`, {
      method: "PATCH", body: JSON.stringify(values),
    });
  },
  ready(slug: string, projectId: number, submissionId: number, revisionId: number) {
    return apiRequest<BidRevision>(`${revisionBase(slug, projectId, submissionId, revisionId)}/ready/`, {
      method: "POST", body: "{}",
    });
  },
  addItem(slug: string, projectId: number, submissionId: number, revisionId: number, values: Record<string, unknown>) {
    return apiRequest<{ id: number }>(`${revisionBase(slug, projectId, submissionId, revisionId)}/items/`, {
      method: "POST", body: JSON.stringify(values),
    });
  },
  updateItem(slug: string, projectId: number, submissionId: number, revisionId: number, itemId: number, values: Record<string, unknown>) {
    return apiRequest<{ id: number }>(`${revisionBase(slug, projectId, submissionId, revisionId)}/items/${itemId}/`, {
      method: "PATCH", body: JSON.stringify(values),
    });
  },
  removeItem(slug: string, projectId: number, submissionId: number, revisionId: number, itemId: number) {
    return apiRequest<void>(`${revisionBase(slug, projectId, submissionId, revisionId)}/items/${itemId}/`, {
      method: "DELETE",
    });
  },
  coverage(slug: string, projectId: number, submissionId: number, revisionId: number, scopeItemId: number, values: Record<string, unknown>) {
    return apiRequest<{ id: number }>(`${revisionBase(slug, projectId, submissionId, revisionId)}/scope-items/${scopeItemId}/`, {
      method: "PUT", body: JSON.stringify(values),
    });
  },
  evidence(slug: string, projectId: number, submissionId: number, revisionId: number, values: Record<string, unknown>) {
    return apiRequest<{ id: number }>(`${revisionBase(slug, projectId, submissionId, revisionId)}/evidence/`, {
      method: "POST", body: JSON.stringify(values),
    });
  },
  removeEvidence(slug: string, projectId: number, submissionId: number, revisionId: number, evidenceId: number) {
    return apiRequest<void>(`${revisionBase(slug, projectId, submissionId, revisionId)}/evidence/${evidenceId}/`, {
      method: "DELETE",
    });
  },
  extractions(slug: string, projectId: number, submissionId: number) {
    return apiRequest<{ runs: BidExtraction[] }>(`${base(slug, projectId, submissionId)}/extractions/`);
  },
  extract(slug: string, projectId: number, submissionId: number, attachmentId: number, requestKey: string) {
    return apiRequest<BidExtraction>(`${base(slug, projectId, submissionId)}/extractions/`, {
      method: "POST", body: JSON.stringify({ attachment_id: attachmentId, request_key: requestKey }),
    });
  },
  candidateDecision(slug: string, projectId: number, submissionId: number, revisionId: number,
                    runId: number, candidateIndex: number, decision: "accepted" | "corrected" | "ignored",
                    corrections: Record<string, unknown> = {}) {
    return apiRequest<{ id: number; decision: string }>(
      `${revisionBase(slug, projectId, submissionId, revisionId)}/extractions/${runId}/decisions/`, {
        method: "POST", body: JSON.stringify({ candidate_index: candidateIndex, decision, corrections }),
      });
  },
};

const BLOCKER_COPY: Record<string, string> = {
  source_quote_missing: "Original quote file required",
  scope_version_not_ready: "Exact trade scope is no longer Ready",
  currency_not_reviewed: "Review currency or confirm it was not stated",
  base_bid_not_reviewed: "Review Base Bid or confirm it was not stated",
  tax_not_reviewed: "Review tax treatment",
  commercial_items_not_reviewed: "Review alternates, allowances, fees, exclusions and conditions",
  scope_not_reviewed: "Review scope coverage and differences",
  scope_coverage_not_reviewed: "Review recorded scope differences",
};
export function bidReadinessCopy(code: string) { return BLOCKER_COPY[code] ?? "Review remaining bid details"; }
