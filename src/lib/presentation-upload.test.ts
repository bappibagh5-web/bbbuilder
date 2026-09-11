import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/documents/production-documents-module.tsx", import.meta.url),
  "utf8",
);

test("production upload accepts PPTX without changing existing file types", () => {
  assert.match(source, /\.pdf,\.pptx,\.docx,\.doc,\.xlsx,\.xls,\.csv,\.txt,\.png,\.jpg,\.jpeg/);
  assert.match(source, /presentationml\.presentation/);
});

test("presentation preparation communicates slide provenance and no OCR or AI", () => {
  assert.match(source, /Native slide text is indexed with slide-number provenance/);
  assert.match(source, /No OCR or AI analysis has run/);
  assert.match(source, /"Slide Index"/);
});
