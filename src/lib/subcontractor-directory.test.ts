import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const page = readFileSync("src/app/(app)/subcontractors/page.tsx", "utf8");
const directory = readFileSync("src/components/subcontractors/subcontractor-directory.tsx", "utf8");
const detail = readFileSync("src/components/subcontractors/subcontractor-detail.tsx", "utf8");

test("global subcontractors route uses production API without demo fixtures", () => {
  assert.doesNotMatch(page, /@\/data/);
  assert.doesNotMatch(directory, /Demo environment|Demo Pacific|Add Demo/);
  assert.match(directory, /contractorsApi\.directory/);
  assert.match(directory, /Loading subcontractors/);
  assert.match(directory, /No subcontractors yet/);
  assert.match(directory, /No subcontractors match these filters/);
});

test("directory supports server filters pagination and real company links", () => {
  assert.match(directory, /Search company or contact/);
  assert.match(directory, /Contact readiness/);
  assert.match(directory, /Previous page/);
  assert.match(directory, /`\/subcontractors\/\$\{company\.id\}`/);
});

test("API errors replace rather than accompany the successful empty state", () => {
  assert.match(directory, /error \? <div role="alert"><State title="Subcontractors unavailable"/);
  assert.doesNotMatch(directory, /\{error &&/);
});

test("company detail explains contextual qualification and links to project workspaces", () => {
  assert.match(detail, /Qualification for this invitation/);
  assert.match(detail, /history_note/);
  assert.match(detail, /section="contractors"/);
  assert.match(detail, /section="outreach"/);
  assert.match(detail, /section="bids"/);
  assert.match(detail, /section="comparisons"/);
  assert.match(detail, /item\.history_count > 1/);
  assert.match(detail, /historical participation records/);
  assert.match(detail, /record\.is_current_scope/);
});
