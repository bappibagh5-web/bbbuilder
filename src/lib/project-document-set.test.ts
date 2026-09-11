import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/documents/production-documents-module.tsx", import.meta.url),
  "utf8",
);

test("project document set groups prepared sources and exposes human include/exclude", () => {
  assert.match(source, /Estimating Document Set/);
  assert.match(source, /Project-wide source selection/);
  assert.match(source, /documentSet\?\.groups\.map/);
  assert.match(source, /"Include in Set"/);
  assert.match(source, /"Exclude from Set"/);
});

test("selection communicates exact revision provenance and coordination uncertainty", () => {
  assert.match(source, /Selection binds the exact document revision/);
  assert.match(source, /pages \/ slides selected/);
  assert.match(source, /Coordination checks/);
  assert.match(source, /not generated scope or approval decisions/);
});

test("viewer document set remains read-only", () => {
  assert.match(source, /disabled=\{!canWrite \|\| !selectable/);
  assert.match(source, /Viewer access is read-only/);
});

test("document set failures use contextual safe messages", () => {
  assert.match(source, /could not be loaded\. Refresh the page/);
  assert.match(source, /ask an administrator to verify database migrations/);
  assert.match(source, /Your previous selection was preserved/);
  assert.match(source, /setError\(documentSetErrorMessage\(reason, "load"\)\)/);
  assert.match(source, /setError\(documentSetErrorMessage\(reason, "update"\)\)/);
});
