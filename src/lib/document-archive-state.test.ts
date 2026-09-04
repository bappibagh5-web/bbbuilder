import assert from "node:assert/strict";
import test from "node:test";
import type { ProductionDocument } from "./documents.ts";
import {
  activeDocuments,
  canManageDocument,
  documentArchiveConfirmation,
  documentArchiveErrorMessage,
  documentStateLabel,
  visibleDocuments,
} from "./document-archive-state.ts";

const documents = [
  { id: 1, is_active: true },
  { id: 2, is_active: false },
] as ProductionDocument[];

test("document lists default cleanly to active and support archived or all views", () => {
  assert.deepEqual(visibleDocuments(documents, "active").map(({ id }) => id), [1]);
  assert.deepEqual(visibleDocuments(documents, "archived").map(({ id }) => id), [2]);
  assert.deepEqual(visibleDocuments(documents, "all").map(({ id }) => id), [1, 2]);
  assert.deepEqual(activeDocuments(documents).map(({ id }) => id), [1]);
});

test("operators receive archive controls while viewers remain read-only", () => {
  assert.equal(canManageDocument("admin"), true);
  assert.equal(canManageDocument("estimator_operator"), true);
  assert.equal(canManageDocument("viewer"), false);
});

test("archive presentation is explicit, reversible, and visibly archived", () => {
  assert.equal(documentArchiveConfirmation.title, "Archive this document?");
  assert.match(documentArchiveConfirmation.detail, /review history remain preserved/i);
  assert.equal(documentStateLabel(documents[1]), "Archived");
});

test("archive failures use safe action-specific copy while preserving controlled reasons", () => {
  assert.equal(
    documentArchiveErrorMessage(new Error("The request could not be completed."), false),
    "We couldn't archive this document.",
  );
  assert.equal(
    documentArchiveErrorMessage(new Error("This document is already archived."), false),
    "This document is already archived.",
  );
  assert.equal(documentArchiveErrorMessage(undefined, true), "We couldn't restore this document.");
});
