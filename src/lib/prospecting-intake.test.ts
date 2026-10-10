import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const intake = readFileSync(
  new URL("../components/prospecting/prospect-intake-actions.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(new URL("./prospecting.ts", import.meta.url), "utf8");
const list = readFileSync(
  new URL("../components/prospecting/prospecting-workspace.tsx", import.meta.url),
  "utf8",
);

test("prospect list exposes separate manual and spreadsheet intake actions", () => {
  assert.match(list, /ProspectIntakeActions/);
  assert.match(intake, /Add prospect manually/);
  assert.match(intake, /Import prospects/);
});

test("manual intake exposes only the simple cold-email fields", () => {
  const manualSection = intake.split('{mode === "import"')[0];
  for (const label of ["Name", "Email", "Phone", "Company", "Trade / category", "Tags", "Notes"]) {
    assert.match(manualSection, new RegExp(label.replace("/", "\\/")));
  }
  for (const removed of [
    "Website",
    "Company email",
    "Address",
    "Postal code",
    "Province / state",
    "Title / role",
    "Make this the company primary contact",
  ]) {
    assert.doesNotMatch(manualSection, new RegExp(removed.replace("/", "\\/")));
  }
  assert.match(api, /prospects\/manual\//);
});

test("import remains preview then explicit confirmation with row-level status", () => {
  assert.match(intake, /Preview import/);
  assert.match(intake, /Import preview/);
  assert.match(intake, /Likely duplicates/);
  assert.match(intake, /Existing companies/);
  assert.match(intake, /Confirm import/);
  assert.match(api, /imports\/\$\{importId\}\/confirm\//);
});

test("prospect list downloads the canonical Excel import template", () => {
  assert.match(intake, /Download Excel template/);
  assert.match(intake, /downloadImportTemplate\(slug\)/);
  assert.match(api, /root\(slug\)\}\/import-template\//);
  assert.match(api, /response\.blob\(\)/);
});
