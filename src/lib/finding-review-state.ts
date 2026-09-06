import type { ExtractedFinding } from "./analysis.ts";
import type { FindingDecision, FindingReview } from "./analysis.ts";

export function findingReviewActions(canOperate: boolean) {
  return {
    canMaterialize: canOperate,
    canReview: canOperate,
    canResolveConflict: canOperate,
    canApproveIntelligence: false,
  };
}

export function reviewProgress(findings: Pick<ExtractedFinding, "review_status" | "handling_status">[]) {
  const reviewed = findings.filter((finding) => finding.review_status !== "unreviewed").length;
  const aiHandled = findings.filter((finding) => finding.handling_status === "ai_handled").length;
  const needsAttention = findings.filter((finding) => ["needs_attention", "conflicting", "human_needs_follow_up"].includes(finding.handling_status)).length;
  return { total: findings.length, reviewed, aiHandled, needsAttention, unreviewed: findings.length - reviewed };
}

function normalizedReviewText(value: string | null | undefined) {
  return (value ?? "").trim();
}

export function canSubmitFindingReview(
  canReview: boolean,
  current: FindingReview | undefined,
  decision: FindingDecision,
  reviewedValue = "",
  reviewNote = "",
) {
  if (!canReview) return false;
  if (!current) return true;
  return !(
    current.decision === decision &&
    normalizedReviewText(current.reviewed_value) === normalizedReviewText(reviewedValue) &&
    normalizedReviewText(current.review_note) === normalizedReviewText(reviewNote)
  );
}

export const REVIEWED_NOT_APPROVED_WARNING =
  "Human reviewed — not yet approved project intelligence.";
