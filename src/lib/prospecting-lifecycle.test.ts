import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const directory = readFileSync(
  new URL("../components/prospecting/prospecting-campaign-directory.tsx", import.meta.url),
  "utf8",
);
const sequence = readFileSync(
  new URL("../components/prospecting/prospecting-sequence-builder.tsx", import.meta.url),
  "utf8",
);
const workspace = readFileSync(
  new URL("../components/prospecting/prospecting-workspace.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(new URL("./prospecting.ts", import.meta.url), "utf8");

test("campaign directory separates active and archived lifecycle actions", () => {
  for (const label of ["Active", "Archived", "Restore"]) {
    assert.match(directory, new RegExp(`>${label}<`));
  }
  assert.match(directory, /\? "Delete" : "Archive"/);
  assert.match(directory, /no future messages will be sent/i);
  assert.match(directory, /Historical delivery and recipient records will be preserved/i);
  assert.match(api, /removeCampaign/);
  assert.match(api, /"archive" \| "restore"/);
});

test("campaign detail and templates expose safe archive and restore controls", () => {
  assert.match(sequence, /Delete campaign/);
  assert.match(sequence, /Archive campaign/);
  assert.match(sequence, /Restore campaign/);
  assert.match(sequence, /Archived templates/);
  assert.match(sequence, /Template updated\. Existing campaign steps were not changed\./);
  assert.match(sequence, /is_active: false/);
  assert.match(sequence, /is_active: true/);
});

test("empty sequence uses the initial-email action before follow-ups", () => {
  assert.match(sequence, /data\.steps\.length === 0 \? "\+ Add initial email" : "\+ Add follow-up"/);
  assert.match(sequence, /delay_minutes: initial \? 0 : 4320/);
  assert.match(sequence, /label: initial \? "Initial Email"/);
});

test("prospect lists default to active and require confirmation to archive or reactivate", () => {
  assert.match(workspace, /useState\("active"\)/);
  assert.match(workspace, /<option value="active">Active<\/option>/);
  assert.match(workspace, /<option value="archived">Archived<\/option>/);
  assert.match(workspace, /Archive this prospect list\?/);
  assert.match(workspace, /Reactivate this prospect list\?/);
});
