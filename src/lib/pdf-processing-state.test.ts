import assert from "node:assert/strict";
import test from "node:test";

import {
  PDF_CHAINING_GRACE_OBSERVATIONS,
  derivePdfProcessingDisplay,
} from "./pdf-processing-state.ts";

const base = {
  isPdf: true,
  sourceStatus: "succeeded" as const,
  missingPdfObservationCount: 0,
  canWrite: true,
};

test("source verification running continues polling without PDF actions", () => {
  const state = derivePdfProcessingDisplay({ ...base, sourceStatus: "running" });
  assert.deepEqual(state, {
    kind: "waiting_for_source",
    shouldPoll: true,
    showIndexAction: false,
  });
});

test("successful source without a PDF job enters a bounded preparing state", () => {
  const state = derivePdfProcessingDisplay(base);
  assert.equal(state.kind, "preparing");
  assert.equal(state.shouldPoll, true);
  assert.equal(state.showIndexAction, false);
});

test("a queued chained PDF job replaces the preparing state", () => {
  assert.equal(derivePdfProcessingDisplay({ ...base, pdfStatus: "queued" }).kind, "queued");
});

test("running PDF indexing remains an active polling state", () => {
  const state = derivePdfProcessingDisplay({ ...base, pdfStatus: "running" });
  assert.equal(state.kind, "running");
  assert.equal(state.shouldPoll, true);
});

test("successful PDF indexing exposes only the backend page count", () => {
  const state = derivePdfProcessingDisplay({
    ...base,
    pdfStatus: "succeeded",
    pdfPageCount: 8,
  });
  assert.equal(state.kind, "succeeded");
  assert.equal(state.pageCount, 8);
  assert.equal(state.shouldPoll, false);
});

test("failed PDF indexing is visible and stops polling", () => {
  const state = derivePdfProcessingDisplay({ ...base, pdfStatus: "failed" });
  assert.equal(state.kind, "failed");
  assert.equal(state.shouldPoll, false);
});

test("historical verified PDFs settle after the bounded chaining grace", () => {
  const state = derivePdfProcessingDisplay({
    ...base,
    missingPdfObservationCount: PDF_CHAINING_GRACE_OBSERVATIONS,
  });
  assert.equal(state.kind, "not_indexed");
  assert.equal(state.shouldPoll, false);
  assert.equal(state.showIndexAction, true);
});

test("viewers never receive the explicit indexing action", () => {
  const state = derivePdfProcessingDisplay({
    ...base,
    missingPdfObservationCount: PDF_CHAINING_GRACE_OBSERVATIONS,
    canWrite: false,
  });
  assert.equal(state.kind, "not_indexed");
  assert.equal(state.showIndexAction, false);
});

test("non-PDF revisions never enter PDF transition or expose actions", () => {
  const state = derivePdfProcessingDisplay({ ...base, isPdf: false });
  assert.equal(state.kind, "not_applicable");
  assert.equal(state.shouldPoll, false);
  assert.equal(state.showIndexAction, false);
});

test("a succeeded PDF job renders immediately on a fresh observation", () => {
  const state = derivePdfProcessingDisplay({
    ...base,
    pdfStatus: "succeeded",
    pdfPageCount: 12,
  });
  assert.equal(state.kind, "succeeded");
  assert.equal(state.pageCount, 12);
});
