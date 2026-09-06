import assert from "node:assert/strict";
import test from "node:test";
import { dashboardActivityLabel, dashboardReviewCounts, projectNeedsAttention } from "./dashboard-state.ts";

test("dashboard review metrics distinguish machine handling from human review", () => {
  const findings = [
    ...Array.from({ length: 23 }, () => ({ handling_status: "ai_handled" as const })),
    ...Array.from({ length: 7 }, () => ({ handling_status: "human_confirmed" as const })),
  ];
  assert.deepEqual(dashboardReviewCounts(findings, []), {
    total: 30,
    aiHandled: 23,
    reviewedByUser: 7,
    needsAttention: 0,
    conflicts: 0,
    complete: true,
  });
});

test("attention includes incomplete document coverage, follow-up, and open conflicts", () => {
  assert.equal(projectNeedsAttention({ activeDocumentCount: 0, reviewedDocumentCount: 0, needsAttention: 0, conflicts: 0 }), true);
  assert.equal(projectNeedsAttention({ activeDocumentCount: 2, reviewedDocumentCount: 1, needsAttention: 0, conflicts: 0 }), true);
  assert.equal(projectNeedsAttention({ activeDocumentCount: 1, reviewedDocumentCount: 1, needsAttention: 1, conflicts: 0 }), true);
  assert.equal(projectNeedsAttention({ activeDocumentCount: 1, reviewedDocumentCount: 1, needsAttention: 0, conflicts: 1 }), true);
  assert.equal(projectNeedsAttention({ activeDocumentCount: 1, reviewedDocumentCount: 1, needsAttention: 0, conflicts: 0 }), false);
});

test("dashboard activity uses client language without exposing metadata", () => {
  assert.equal(dashboardActivityLabel("intelligence_snapshot.approved"), "Project information approved");
  assert.equal(dashboardActivityLabel("custom.event"), "custom · event");
});
