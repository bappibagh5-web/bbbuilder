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
