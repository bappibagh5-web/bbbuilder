import assert from "node:assert/strict";
import test from "node:test";
import { analysisActions, deriveAnalysisState, MACHINE_REVIEW_WARNING, projectSetCoverageLabel, shouldPollAnalysis } from "./analysis-state.ts";

test("analysis readiness requires verified indexed PDF pages", () => {
  assert.equal(deriveAnalysisState({ isPdf: false, pageCount: 0 }), "unsupported");
  assert.equal(deriveAnalysisState({ isPdf: true, pageCount: 0 }), "source_required");
  assert.equal(deriveAnalysisState({ isPdf: true, sourceStatus: "succeeded", pageCount: 0 }), "index_required");
  assert.equal(deriveAnalysisState({ isPdf: true, sourceStatus: "succeeded", pdfStatus: "succeeded", pageCount: 2 }), "ready");
});

test("persisted run states take precedence after prerequisites", () => {
  for (const status of ["queued", "running", "succeeded", "failed", "cancelled"] as const) {
    assert.equal(deriveAnalysisState({ isPdf: true, sourceStatus: "succeeded", pdfStatus: "succeeded", pageCount: 2, runStatus: status }), status);
  }
});

test("viewer never receives paid run, retry, or cancellation actions", () => {
  for (const state of ["ready", "succeeded", "failed", "queued", "running"] as const) {
    assert.equal(Object.values(analysisActions(state, false)).some(Boolean), false);
  }
});

test("operators receive the correct revision-level explicit action", () => {
  assert.equal(analysisActions("ready", true).canRun, true);
  assert.equal(analysisActions("succeeded", true).canRunAgain, true);
  assert.equal(analysisActions("failed", true).canRetry, true);
  assert.equal(analysisActions("cancelled", true).canRetry, true);
  assert.equal(analysisActions("queued", true).canCancel, true);
  assert.equal(analysisActions("running", true).canCancel, true);
});

test("unsupported and unindexed revisions never expose analysis actions", () => {
  assert.equal(Object.values(analysisActions("unsupported", true)).some(Boolean), false);
  assert.equal(Object.values(analysisActions("index_required", true)).some(Boolean), false);
});

test("historical selection does not replace latest revision action state", () => {
  const history = [{ id: 4, status: "succeeded" }, { id: 3, status: "succeeded" }];
  const selectedHistoricalRun = history[1];
  const latestRun = history[0];
  assert.equal(selectedHistoricalRun.id, 3);
  assert.equal(analysisActions(deriveAnalysisState({ isPdf: true, sourceStatus: "succeeded", pdfStatus: "succeeded", pageCount: 3, runStatus: latestRun.status }), true).canRunAgain, true);
  assert.deepEqual(history.map((run) => run.id), [4, 3]);
});

test("fresh reload with a succeeded latest run exposes re-analysis", () => {
  const state = deriveAnalysisState({ isPdf: true, sourceStatus: "succeeded", pdfStatus: "succeeded", pageCount: 3, runStatus: "succeeded" });
  assert.equal(analysisActions(state, true).canRunAgain, true);
});

test("polling is bounded and stops at terminal persisted states", () => {
  assert.equal(shouldPollAnalysis("queued", 0), true);
  assert.equal(shouldPollAnalysis("running", 59), true);
  assert.equal(shouldPollAnalysis("running", 2159), true);
  assert.equal(shouldPollAnalysis("running", 2160), false);
  assert.equal(shouldPollAnalysis("succeeded", 0), false);
  assert.equal(shouldPollAnalysis("failed", 0), false);
  assert.equal(shouldPollAnalysis("cancelled", 0), false);
});

test("machine output warning does not imply human approval", () => {
  assert.equal(MACHINE_REVIEW_WARNING, "Machine generated — not yet human reviewed.");
  assert.equal(MACHINE_REVIEW_WARNING.includes("approve"), false);
});

test("project-set coverage is presented as one coordinated review", () => {
  assert.equal(projectSetCoverageLabel(23, 141), "23 documents · 141 pages/slides");
});
