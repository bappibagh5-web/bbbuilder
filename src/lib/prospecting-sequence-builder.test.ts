import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workspace = readFileSync(
  new URL("../components/prospecting/prospecting-sequence-builder.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(new URL("./prospecting.ts", import.meta.url), "utf8");

test("campaign detail uses ordered cold-email sequence controls", () => {
  for (const label of [
    "Cold email sequence",
    "+ Add follow-up",
    "Send immediately",
    "Insert in subject:",
    "Insert in body:",
    "Duplicate",
    "Move up",
    "Move down",
    "Disable",
    "Save draft",
  ]) assert.match(workspace, new RegExp(label.replace(/[+]/g, "\\+")));
  assert.match(workspace, /minutes/);
  assert.match(workspace, /hours/);
  assert.match(workspace, /days/);
});

test("preview, explicit test recipient, and reusable templates are production backed", () => {
  assert.match(workspace, /Preview as prospect/);
  assert.match(workspace, /Explicit test recipient email/);
  assert.match(workspace, /Send test email/);
  assert.match(workspace, /Save as template/);
  assert.match(workspace, /Use template/);
  assert.match(api, /previewCampaignStep/);
  assert.match(api, /sendTestEmail/);
  assert.match(api, /createTemplate/);
  assert.match(api, /reorderSteps/);
});

test("supported personalization tokens are offered without HTML designer controls", () => {
  for (const token of ["first_name", "name", "company_name", "trade"]) {
    assert.match(workspace, new RegExp(token));
  }
  assert.doesNotMatch(workspace, /drag-and-drop|image block|newsletter/i);
});
