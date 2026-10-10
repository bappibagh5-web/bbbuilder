import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../components/prospecting/prospecting-p2-workspace.tsx", import.meta.url), "utf8");
const unsubscribe = readFileSync(new URL("../components/prospecting/unsubscribe-page.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("./prospecting.ts", import.meta.url), "utf8");

test("campaigns require explicit approval and launch with readiness blockers", () => {
  assert.match(source, /Approve content & recipients/);
  assert.match(source, /Launch campaign/);
  assert.match(source, /Not ready to launch/);
  assert.match(source, /Sequence editor/);
  assert.match(api, /campaignAction/);
});

test("prospecting delivery remains distinct from project outreach", () => {
  assert.doesNotMatch(source, /InvitationCampaign|InvitationRecipient|RFQ/);
  assert.match(source, /separate from project bid outreach/);
  assert.match(source, /Process due sends now/);
});

test("settings save and due-send errors render inline instead of escaping event handlers", () => {
  assert.match(source, /async function save\(\)/);
  assert.match(source, /async function processDue\(\)/);
  assert.match(source, /catch \(reason\)[\s\S]*setError/);
  assert.match(source, /role="alert"/);
  assert.doesNotMatch(source, /prospectingApi\.processDue\(slug\)\.then/);
});

test("suppression and analytics have production APIs and Viewer-safe controls", () => {
  assert.match(source, /Manual suppression/);
  assert.match(source, /Removing suppression never restarts/);
  assert.match(source, /data\.can_admin/);
  assert.match(api, /suppressions/);
  assert.match(api, /analytics/);
});

test("public unsubscribe supports confirm success repeat and invalid states", () => {
  assert.match(unsubscribe, /Confirm unsubscribe/);
  assert.match(unsubscribe, /already_unsubscribed/);
  assert.match(unsubscribe, /invalid/);
  assert.match(api, /prospecting\/unsubscribe/);
});
