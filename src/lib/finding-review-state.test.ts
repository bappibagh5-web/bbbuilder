import assert from "node:assert/strict";
import test from "node:test";
import {
  findingReviewActions,
  canSubmitFindingReview,
  REVIEWED_NOT_APPROVED_WARNING,
  reviewProgress,
} from "./finding-review-state.ts";

test("successful analysis can enter materialized review state without final approval", () => {
  assert.deepEqual(findingReviewActions(true), {
    canMaterialize: true,
    canReview: true,
    canResolveConflict: true,
    canApproveIntelligence: false,
  });
});

test("viewer receives read-only finding and conflict state", () => {
  assert.deepEqual(findingReviewActions(false), {
    canMaterialize: false,
    canReview: false,
    canResolveConflict: false,
    canApproveIntelligence: false,
  });
});

test("review progress counts accepted edited rejected and clarification as reviewed", () => {
  assert.deepEqual(
    reviewProgress([
      { review_status: "unreviewed" },
      { review_status: "accepted" },
      { review_status: "edited_accepted" },
      { review_status: "rejected" },
      { review_status: "needs_clarification" },
    ]),
    { total: 5, reviewed: 4, unreviewed: 1 },
  );
});

test("review wording never implies final approval", () => {
  assert.equal(REVIEWED_NOT_APPROVED_WARNING.includes("not yet approved"), true);
});

const currentReview = {
  id: 1,
  finding: 2,
  reviewer: "reviewer@example.com",
  decision: "needs_clarification" as const,
  reviewed_value: "",
  review_note: "",
  supersedes: null,
  created_at: "2026-09-03T00:00:00Z",
};

test("current effective state does not enable a redundant same-state action", () => {
  assert.equal(
    canSubmitFindingReview(true, currentReview, "needs_clarification", "", "   "),
    false,
  );
});

test("meaningful note changes and other state transitions remain available", () => {
  assert.equal(
    canSubmitFindingReview(true, currentReview, "needs_clarification", "", "Architect reply pending"),
    true,
  );
  assert.equal(canSubmitFindingReview(true, currentReview, "accepted"), true);
  assert.equal(canSubmitFindingReview(true, currentReview, "rejected"), true);
  assert.equal(canSubmitFindingReview(false, currentReview, "accepted"), false);
});
