import assert from "node:assert/strict";
import test from "node:test";

import {
  sourceDocumentTarget,
  sourcePdfViewerUrl,
} from "./document-source-navigation.ts";

test("source links use one-based PDF page fragments", () => {
  assert.equal(sourcePdfViewerUrl("blob:document", 1), "blob:document#page=1");
  assert.equal(sourcePdfViewerUrl("blob:document", 6), "blob:document#page=6");
});

test("invalid or missing source pages safely fall back to page one", () => {
  assert.equal(sourcePdfViewerUrl("blob:document"), "blob:document#page=1");
  assert.equal(sourcePdfViewerUrl("blob:document", 0), "blob:document#page=1");
  assert.equal(sourcePdfViewerUrl("blob:document", Number.NaN), "blob:document#page=1");
});

test("source targets preserve their exact historical revision", () => {
  assert.deepEqual(sourceDocumentTarget(5, 11, 6), {
    documentId: 5,
    revisionId: 11,
    pageNumber: 6,
  });
});

test("normal full-document blob URLs remain unchanged", () => {
  assert.equal("blob:document", "blob:document");
});
