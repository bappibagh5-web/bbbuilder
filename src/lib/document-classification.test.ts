import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { suggestDocumentClassification } from "./document-classification.ts";

test("IFC discipline suffixes suggest drawing classifications", () => {
  assert.deepEqual(suggestDocumentClassification("JD_INTERCITY_A_IFC.pdf"), {
    category: "drawings",
    discipline: "architectural",
    explanation: "Suggested from the selected filename. Confirm before applying.",
  });
  assert.equal(suggestDocumentClassification("JD_INTERCITY_M_IFC.pdf")?.discipline, "mechanical");
  assert.equal(suggestDocumentClassification("JD_INTERCITY_E_IFC.pdf")?.discipline, "electrical");
});

test("narrative filenames suggest Narrative plus their discipline", () => {
  assert.deepEqual(suggestDocumentClassification("JD_NARRATIVE_M.pdf"), {
    category: "narrative",
    discipline: "mechanical",
    explanation: "Suggested from the selected filename. Confirm before applying.",
  });
  assert.equal(suggestDocumentClassification("NARRATIVE_E.pdf")?.discipline, "electrical");
});

test("ambiguous filenames remain unsuggested instead of forcing a guess", () => {
  assert.equal(suggestDocumentClassification("project-information.pdf"), null);
});

test("upload UI requires an explicit action before applying a suggestion", () => {
  const source = readFileSync(
    new URL("../components/documents/production-documents-module.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /setSuggestion\(selectedFile \? suggestDocumentClassification/);
  assert.match(source, />\s*Apply suggestion\s*</);
  assert.match(source, /setCategory\(suggestion\.category\)/);
  assert.match(source, /setDiscipline\(suggestion\.discipline\)/);
});
