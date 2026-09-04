import assert from "node:assert/strict";
import test from "node:test";
import type { IntelligenceSnapshot } from "./analysis.ts";
import {
  categoryLabel,
  decisionLabel,
  documentReviewScopeCopy,
  emptyActiveDocumentReviewCopy,
  documentVersionLabel,
  plainAnalysisStatus,
  progressPresentation,
  reviewCounts,
  reviewStages,
  reviewSectionVisibility,
  snapshotPresentation,
  versionSummary,
  versionDetailsButtonLabel,
  versionDetailsInitiallyExpanded,
} from "./document-review-presentation.ts";

test("maps technical categories and decisions to client language", () => {
  assert.equal(categoryLabel("submittal_closeout"), "Submittal / Closeout Requirements");
  assert.equal(categoryLabel("open_question"), "Questions to Follow Up");
  assert.equal(decisionLabel("edited_accepted"), "Confirmed");
  assert.equal(decisionLabel("rejected"), "Not relevant");
  assert.equal(decisionLabel("needs_clarification"), "Needs follow-up");
});

test("distinguishes selected-document review from project-wide approval", () => {
  assert.equal(documentReviewScopeCopy.selectedDocument, "This section shows what AI found in the selected document.");
  assert.equal(documentReviewScopeCopy.projectWideHeading, "Project Information for Approval");
  assert.equal(documentReviewScopeCopy.projectWideBadge, "Project-wide");
  assert.match(documentReviewScopeCopy.projectWideExplanation, /current project documents/);
});

test("zero active documents preserve project-wide historical information", () => {
  assert.deepEqual(reviewSectionVisibility(0), {
    showActiveDocumentReview: false,
    showActiveEmptyState: true,
    showReviewWithAi: false,
    showProjectWideHistory: true,
  });
  assert.equal(emptyActiveDocumentReviewCopy.title, "No active documents ready for review");
  assert.match(emptyActiveDocumentReviewCopy.detail, /Restore an archived document/);
});

test("active document review and project-wide history render together", () => {
  assert.deepEqual(reviewSectionVisibility(1), {
    showActiveDocumentReview: true,
    showActiveEmptyState: false,
    showReviewWithAi: true,
    showProjectWideHistory: true,
  });
});

test("distinguishes current and older document versions", () => {
  assert.equal(documentVersionLabel(true, "R1", 7), "Current Version (R1)");
  assert.equal(documentVersionLabel(false, "R2", 8), "Older Document Version (R2)");
});

test("review counts distinguish complete and attention states", () => {
  assert.deepEqual(reviewCounts([{ review_status: "accepted" }, { review_status: "rejected" }, { review_status: "needs_clarification" }]), {
    total: 3, reviewed: 3, confirmed: 1, notRelevant: 1, followUp: 1, unreviewed: 0, needsAttention: 1, complete: false,
  });
  assert.equal(reviewCounts([{ review_status: "accepted" }, { review_status: "rejected" }]).complete, true);
});

test("an untouched document never presents misleading zero-of-zero progress", () => {
  const counts = reviewCounts([]);
  assert.deepEqual(progressPresentation(false, counts), {
    heading: "Not reviewed yet",
    detail: "AI review has not been started for this document.",
    nextStep: "Review this document with AI.",
  });
  assert.doesNotMatch(progressPresentation(false, counts).heading, /0 \/ 0/);
});

test("project information version summary counts included and not-relevant items", () => {
  const snapshot = {
    sources: [{ document_title: "Mechanical Drawings", revision_label: "R1", document_revision: 7, entries: [
      { included_in_intelligence: true },
      { included_in_intelligence: false },
      { included_in_intelligence: false },
    ] }],
  } as IntelligenceSnapshot;
  assert.deepEqual(versionSummary(snapshot), {
    included: 1,
    notRelevant: 2,
    sources: ["Mechanical Drawings — R1"],
  });
});

test("version manifest is collapsed by default and exposes an explicit toggle", () => {
  assert.equal(versionDetailsInitiallyExpanded, false);
  assert.equal(versionDetailsButtonLabel(false), "View version details");
  assert.equal(versionDetailsButtonLabel(true), "Hide version details");
});

test("stage mapping uses existing persisted states without another workflow", () => {
  const stages = reviewStages({ uploaded: true, sourceStatus: "succeeded", pdfStatus: "succeeded", pageCount: 8, runStatus: "succeeded", findingCount: 8, needsAttention: 1, approved: false });
  assert.deepEqual(stages.map((stage) => stage.label), ["Uploaded", "Prepared", "AI Review", "Your Review", "Approved"]);
  assert.deepEqual(stages.map((stage) => stage.state), ["completed", "completed", "completed", "current", "upcoming"]);
  const approved = reviewStages({ uploaded: true, sourceStatus: "succeeded", pdfStatus: "succeeded", pageCount: 8, runStatus: "succeeded", findingCount: 8, needsAttention: 0, approved: true });
  assert.ok(approved.every((stage) => stage.state === "completed"));
});

test("loading error and approval history use plain-language labels", () => {
  assert.equal(plainAnalysisStatus("running"), "AI is reviewing your document");
  assert.equal(plainAnalysisStatus("failed"), "We couldn't finish reviewing this document");
  const snapshot = { approval: null, is_stale: true } as IntelligenceSnapshot;
  assert.equal(snapshotPresentation(snapshot), "Update required");
  assert.equal(snapshotPresentation({ ...snapshot, is_stale: false }), "Ready for approval");
});
