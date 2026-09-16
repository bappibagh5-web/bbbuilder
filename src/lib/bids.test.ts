import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const bids = readFileSync(new URL("../components/bids/production-bids-module.tsx", import.meta.url), "utf8");
const outreach = readFileSync(new URL("../components/outreach/production-outreach-module.tsx", import.meta.url), "utf8");
const workspace = readFileSync(new URL("../components/projects/production-project-workspace.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("./bids.ts", import.meta.url), "utf8");

test("numeric Bids tab uses private production quote intake, never demo inbox", () => {
  assert.match(workspace, /section === "bids" \? <ProductionBidsModule/);
  assert.match(bids, /No quotes have been recorded for this project/);
  assert.match(bids, /Exact scope version/);
  assert.match(api, /apiResponse\(`\$\{base\(slug, projectId\)\}\/bid-submissions\/\$\{submissionId\}\/attachments\/\$\{attachmentId\}\/download\/`\)/);
});

test("manual intake requires an exact invitation, received time and original files", () => {
  assert.match(bids, /Select invitation recipient/);
  assert.match(bids, /type="file" multiple/);
  assert.match(bids, /!recipientId \|\| !receivedAt \|\| files\.length === 0/);
  assert.match(api, /body\.set\("request_key", requestKey\)/);
  assert.match(bids, /membership\.role === "admin" \|\| membership\.role === "estimator_operator"/);
});

test("inbound quote import is explicit and Viewer cannot trigger it", () => {
  assert.match(outreach, /Import Quote/);
  assert.match(outreach, /canEdit && <button/);
  assert.match(outreach, /bidsApi\.importReceived/);
  assert.match(outreach, /setImportFailures/);
  assert.match(outreach, /importFailures\[item\.id\] && <p role="alert"/);
  assert.match(outreach, /await refresh\(\)/);
  assert.match(outreach, /Quote attachment received/);
  assert.match(outreach, /Stored quote submissions/);
  assert.match(outreach, /Download privately/);
});

test("inbox separates received intake from structured bid readiness", () => {
  assert.match(api, /structured_status: "not_started" \| "draft" \| "ready"/);
  assert.match(bids, /Structured bid: /);
  assert.match(bids, /Ready for Comparison/);
  assert.match(bids, /Not started/);
  assert.match(bids, /setSelectedQuoteId\(0\); void refresh\(\)/);
});
