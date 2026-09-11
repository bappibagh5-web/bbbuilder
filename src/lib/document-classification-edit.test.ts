import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/documents/production-documents-module.tsx", import.meta.url),
  "utf8",
);

test("operators can open the metadata-only classification editor", () => {
  assert.match(source, />\s*Edit Classification\s*</);
  assert.match(source, /canWrite && \(\s*<button/);
  assert.match(source, /onClick=\{\(\) => setClassificationDocument\(document\)\}/);
  assert.match(source, /This updates metadata only/);
});

test("classification save sends only type and discipline and updates local document state", () => {
  assert.match(source, /documentsApi\.update[\s\S]*?\{\s*category,\s*discipline,\s*\}/);
  assert.match(source, /setDocuments\(\(current\) => current\.map/);
  assert.match(source, /Files, revisions, and review history were unchanged/);
});

test("viewer does not receive edit classification controls", () => {
  assert.match(source, /const canWrite = project\.is_active && canManageArchive/);
  assert.match(source, /canWrite && \(\s*<button/);
  assert.match(source, /setClassificationDocument\(document\)/);
});
