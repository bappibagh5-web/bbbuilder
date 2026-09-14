import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/outreach/production-outreach-module.tsx", import.meta.url),
  "utf8",
);

test("Outreach requires explicit campaign, batch, candidate, contact, and send gates", () => {
  assert.match(source, /Create Draft Campaign/);
  assert.match(source, /Create Next Batch/);
  assert.match(source, /Select contact/);
  assert.match(source, /Add Recipient/);
  assert.match(source, /No contractor is added automatically/);
  assert.match(source, /Send readiness/);
  assert.match(source, /batch\?\.delivery_readiness \?\?/);
  assert.match(source, /code: "readiness_unavailable"/);
  assert.match(source, /delivery\.blockers/);
  assert.match(source, /Approve Sending/);
  assert.match(source, /Prepare Messages/);
  assert.match(source, /Send Invitations/);
  assert.match(source, /window\.confirm/);
  assert.match(source, /Retry explicitly/);
});

test("Viewer can inspect preparation, RFQ, and attempt history but cannot mutate it", () => {
  assert.match(source, /membership\.role === "admin" \|\| membership\.role === "estimator_operator"/);
  assert.match(source, /Preview RFQ/);
  assert.match(source, /canPrepare && <button/);
  assert.match(source, /canPrepare && <div/);
  assert.match(source, /message\.attempts\.map/);
});

test("campaign setup and exact immutable message are reviewed before human send approval", () => {
  assert.match(source, /Bid Deadline/);
  assert.match(source, /Questions Deadline \(optional\)/);
  assert.match(source, /Save Campaign Setup/);
  assert.match(source, /Review exact message before approval/);
  assert.match(source, /message\.source_scope_version_id|message\.scope_version_id/);
  assert.match(source, /Approve the exact prepared message versions/);
  assert.match(source, /delivery\.ready/);
});

test("SMTP setup and sender settings are Admin-managed with explicit network actions", () => {
  const settings = readFileSync(new URL("../components/settings-panel.tsx", import.meta.url), "utf8");
  assert.match(settings, /activeMembership\?\.role === "admin"/);
  assert.match(settings, /Save sender settings/);
  assert.match(settings, /Email Delivery \/ SMTP Setup/);
  assert.match(settings, /Test SMTP Connection/);
  assert.match(settings, /Send Test Email/);
  assert.match(settings, /setConnectionResult\(\{ success: result.success/);
  assert.match(settings, /Authentication failed/);
  assert.match(settings, /TLS\/SSL error/);
  assert.match(settings, /testEmailBlockers\.length > 0/);
  assert.match(settings, /Configure sender identity/);
  assert.match(settings, /Enter a test recipient/);
  assert.match(settings, /window\.confirm/);
  assert.match(settings, /Password saved securely/);
  assert.match(settings, /password: ""/);
  assert.doesNotMatch(settings, /OUTREACH_SMTP_PASSWORD|Simulated — no emails are sent/);
});
