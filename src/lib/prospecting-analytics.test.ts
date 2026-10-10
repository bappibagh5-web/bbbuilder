import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const dashboard = readFileSync(new URL("../components/prospecting/prospecting-analytics-dashboard.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("./prospecting.ts", import.meta.url), "utf8");

test("analytics renders bounded KPI and period controls", () => {
  assert.match(dashboard, /Prospects contacted/);
  assert.match(dashboard, /Emails sent/);
  assert.match(dashboard, /Last 30 days/);
  assert.match(dashboard, /Performance trend/);
});

test("campaign and sequence performance remain read-only", () => {
  assert.match(dashboard, /Campaign performance/);
  assert.match(dashboard, /Performance by sequence step/);
  assert.match(dashboard, /Open campaign/);
  assert.doesNotMatch(dashboard, /Send now|Resend|Launch campaign/);
});

test("recipient engagement supports filters search and activity detail", () => {
  assert.match(dashboard, /Recipient engagement/);
  assert.match(dashboard, /not_opened/);
  assert.match(dashboard, /Search name, company, email/);
  assert.match(dashboard, /Recipient activity/);
});

test("tracking unavailable and provider-open caveat are explicit", () => {
  assert.match(dashboard, /Tracking status/);
  assert.match(dashboard, /provider-reported/);
  assert.match(dashboard, /Awaiting events/);
});

test("analytics API uses bounded overview campaign and recipient endpoints", () => {
  assert.match(api, /analyticsCampaigns/);
  assert.match(api, /analyticsCampaign/);
  assert.match(api, /analyticsRecipients/);
  assert.match(api, /analyticsRecipient/);
});
