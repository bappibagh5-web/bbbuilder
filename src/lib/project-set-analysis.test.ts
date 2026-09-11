import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const panel = readFileSync(
  new URL(
    "../components/documents/production-documents-module.tsx",
    import.meta.url,
  ),
  "utf8",
);
const client = readFileSync(new URL("./analysis.ts", import.meta.url), "utf8");
const review = readFileSync(
  new URL("../components/ai-review/production-ai-review-module.tsx", import.meta.url),
  "utf8",
);

test("project-set review starts only from an explicit operator action", () => {
  assert.match(panel, /Review Project Set/);
  assert.match(panel, /Prepare Items for Review/);
  assert.match(panel, /Preparing saved results does not call the provider/);
  assert.match(panel, /onClick=\{\(\) => void startProjectReview\(\)\}/);
  assert.match(panel, /It never auto-starts when documents are selected/);
  assert.match(panel, /documentSet\.included_document_count === 0/);
});

test("project-set review exposes durable live page progress", () => {
  assert.match(panel, /projectSetRuns/);
  assert.match(panel, /requestProjectSetRun/);
  assert.match(panel, /progress\.completed/);
  assert.match(panel, /progress\.total/);
  assert.match(panel, /window\.setInterval/);
});

test("analysis client uses project-scoped project-set endpoint", () => {
  assert.match(client, /project-set-analysis-runs/);
  assert.match(client, /project-review-state/);
  assert.match(client, /project-review-findings/);
  assert.match(client, /ProjectReviewState/);
  assert.match(client, /ProjectReviewFindingPage/);
  assert.match(client, /run_kind: "document" \| "project_set"/);
  assert.match(client, /document_revision_ids/);
  assert.match(client, /source_priority/);
});

test("Document Review defaults to one project-wide review with document drill-down", () => {
  assert.match(review, /useState<"project" \| "document">\("project"\)/);
  assert.match(review, /Project Review/);
  assert.match(review, /Project findings/);
  assert.match(review, /Trade coverage/);
  assert.match(review, /View individual document/);
  assert.match(review, /LazyProjectReviewPanel/);
  assert.match(review, /projectReviewFindings/);
  assert.match(review, /Load more/);
  assert.match(review, /conflict groups · \{items\} conflicting items/);
  assert.match(review, /useState<string \| null>\(null\)/);
  assert.match(review, /aria-expanded=\{expanded\}/);
  assert.match(review, /expanded &&/);
  assert.match(review, /setExpandedTrade\(null\)/);
  assert.match(review, /Current project-wide review/);
  assert.match(review, /History · \{historicalCandidates\.length\} earlier reviews/);
  assert.match(review, /conflict\.status === "open"/);
  assert.match(review, /conflict\.status !== "open"/);
  assert.match(review, /No conflicts need review/);
  assert.match(review, /Resolved and dismissed conflict history/);
  assert.match(review, /projectReviewLoading/);
  assert.match(review, /analysisApi\.projectReviewState/);
  assert.match(review, /requestId !== projectReviewRequest\.current/);
});
