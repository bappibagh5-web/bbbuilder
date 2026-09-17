import { apiRequest } from "@/lib/api-client";

export type BidHumanDecisionState = "undecided" | "shortlisted" | "not_shortlisted";
export type BidHumanReviewOutcome = "" | "selected_for_proposal" | "no_acceptable_bid";

export type BidHumanDecision = {
  id: number;
  entry_id: number;
  revision_id: number;
  company_name: string;
  state: BidHumanDecisionState;
  note: string;
  decided_by_id: number | null;
  decided_at: string | null;
  source_base_bid: string | null;
  currency: string;
  evaluated_amount: string | null;
};

export type BidHumanReview = {
  id: number;
  sequence: number;
  status: "draft" | "finalized";
  comparison_id: number;
  scope_package_id: number;
  scope_version_id: number;
  supersedes_id: number | null;
  outcome: BidHumanReviewOutcome;
  selected_entry_id: number | null;
  selected_company_name: string | null;
  rationale: string;
  created_by_id: number;
  created_at: string;
  finalized_by_id: number | null;
  finalized_by_name: string | null;
  finalized_at: string | null;
  blockers: string[];
  decisions: BidHumanDecision[];
};

function base(slug: string, projectId: number, comparisonId: number) {
  return `/organizations/${encodeURIComponent(slug)}/projects/${projectId}/bid-comparisons/${comparisonId}/human-reviews`;
}

export const bidHumanReviewsApi = {
  list(slug: string, projectId: number, comparisonId: number, signal?: AbortSignal) {
    return apiRequest<{ reviews: BidHumanReview[]; current: BidHumanReview | null }>(
      `${base(slug, projectId, comparisonId)}/`,
      { signal },
    );
  },
  create(slug: string, projectId: number, comparisonId: number) {
    return apiRequest<BidHumanReview>(`${base(slug, projectId, comparisonId)}/`, {
      method: "POST",
      body: "{}",
    });
  },
  updateOutcome(
    slug: string,
    projectId: number,
    comparisonId: number,
    reviewId: number,
    values: { outcome: BidHumanReviewOutcome; selected_entry_id: number | null; rationale: string },
  ) {
    return apiRequest<BidHumanReview>(`${base(slug, projectId, comparisonId)}/${reviewId}/`, {
      method: "PATCH",
      body: JSON.stringify(values),
    });
  },
  updateDecision(
    slug: string,
    projectId: number,
    comparisonId: number,
    reviewId: number,
    decisionId: number,
    values: { state: BidHumanDecisionState; note: string },
  ) {
    return apiRequest<BidHumanReview>(
      `${base(slug, projectId, comparisonId)}/${reviewId}/decisions/${decisionId}/`,
      { method: "PATCH", body: JSON.stringify(values) },
    );
  },
  finalize(slug: string, projectId: number, comparisonId: number, reviewId: number) {
    return apiRequest<BidHumanReview>(
      `${base(slug, projectId, comparisonId)}/${reviewId}/finalize/`,
      { method: "POST", body: "{}" },
    );
  },
};
