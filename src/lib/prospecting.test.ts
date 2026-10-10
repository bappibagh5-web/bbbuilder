import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../components/prospecting/prospecting-workspace.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("./prospecting.ts", import.meta.url), "utf8");
const navigation = readFileSync(new URL("../components/app-shell.tsx", import.meta.url), "utf8");

test("Prospecting is a distinct organization-level production destination", () => {
  assert.match(navigation, /label: "Prospecting", href: "\/prospecting"/);
  assert.match(api, /organizations.*prospecting/);
  assert.doesNotMatch(source, /InvitationCampaign|InvitationRecipient|RFQ/);
});

test("discovery is explicit and selected results are added to a chosen list", () => {
  assert.match(source, /Search contractors/);
  assert.match(source, /addSelected/);
  assert.match(api, /discoveries\/\$\{runId\}\/add/);
  assert.match(source, /already_in_directory/);
  assert.match(source, /already_on_selected_list/);
});

test("Viewer is read only while operators receive list and enrichment actions", () => {
  assert.match(source, /activeMembership\.role !== "viewer"/);
  assert.match(source, /disabled=\{!canManage \|\| busy\}/);
  assert.match(source, /Find contact information/);
  assert.match(source, /Save and select contact/);
});

test("prospect lists expose loading error empty filters and safe company links", () => {
  assert.match(source, /Loading lists/);
  assert.match(source, /No prospect lists found/);
  assert.match(source, /role="alert"/);
  assert.match(source, /Search lists/);
  assert.match(source, /subcontractors\/\$\{entry\.company\.id\}/);
  assert.match(source, /Pagination/);
  assert.match(source, /Archive list/);
  assert.match(source, /Edit notes & tags/);
  assert.match(source, /Primary contact for/);
  assert.match(source, /Remove/);
});
