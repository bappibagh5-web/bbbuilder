import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { dashboardActivityLabel, dashboardAttentionDescription } from "./dashboard-state.ts";

test("completed project-set review does not imply missing standalone document reviews", () => {
  const description = dashboardAttentionDescription({
    project_review: { current: true },
    review: { total: 556, complete: true, needs_attention: 0, conflicts: 0 },
    active_document_count: 24,
    reviewed_document_count: 0,
  });
  assert.equal(description, "");
});

test("project-set follow-up describes currentness and genuine review exceptions", () => {
  assert.equal(dashboardAttentionDescription({
    project_review: { current: false },
    review: { total: 2, complete: false, needs_attention: 1, conflicts: 1 },
    active_document_count: 24,
    reviewed_document_count: 0,
  }), "Estimating set changed since review · 1 finding needs follow-up · 1 open conflict");
  assert.equal(dashboardAttentionDescription({
    project_review: null,
    review: { total: 1, complete: false, needs_attention: 0, conflicts: 0 },
    active_document_count: 2,
    reviewed_document_count: 1,
  }), "1 current document not fully reviewed");
});

test("dashboard activity uses client language without exposing metadata", () => {
  assert.equal(dashboardActivityLabel("intelligence_snapshot.approved"), "Project information approved");
  assert.equal(dashboardActivityLabel("custom.event"), "custom · event");
});

test("production dashboard uses summary-first APIs without a project-document waterfall", () => {
  const source = readFileSync(
    new URL("../components/dashboard/production-dashboard.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /dashboardApi\.summary/);
  assert.match(source, /dashboardApi\.activity/);
  assert.doesNotMatch(source, /documentsApi\.list/);
  assert.doesNotMatch(source, /analysisApi\.(findings|conflicts|snapshots|list)/);
  assert.doesNotMatch(source, /projectsApi\.auditEvents/);
  assert.doesNotMatch(source, /Loading your preconstruction dashboard/);
});

test("dashboard keeps useful structure and independent activity loading", () => {
  const source = readFileSync(
    new URL("../components/dashboard/production-dashboard.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /<header/);
  assert.match(source, /<DashboardSkeleton/);
  assert.match(source, /Showing the last loaded dashboard/);
  assert.match(source, /activityLoading/);
  assert.match(source, /Recent activity is temporarily unavailable/);
});

test("dashboard metric cards use the summary API's snake_case review fields", () => {
  const source = readFileSync(
    new URL("../components/dashboard/production-dashboard.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /value=\{review\.ai_handled\}/);
  assert.match(source, /value=\{review\.reviewed_by_user\}/);
  assert.match(source, /value=\{review\.needs_attention \+ review\.conflicts\}/);
  assert.doesNotMatch(source, /review\.(aiHandled|reviewedByUser|needsAttention)/);
  assert.match(source, /Project reviews complete/);
  assert.match(source, /Estimating set reviewed/);
  assert.match(source, /project_reviews_complete/);
  assert.doesNotMatch(source, /Document reviews complete/);
});
