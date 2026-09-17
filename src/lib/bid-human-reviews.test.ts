import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workspace = readFileSync("src/components/comparisons/human-bid-review.tsx", "utf8");
const comparison = readFileSync("src/components/comparisons/production-bid-comparisons.tsx", "utf8");
const api = readFileSync("src/lib/bid-human-reviews.ts", "utf8");

test("human review starts with nothing preselected and explicit bidder controls", () => {
  assert.match(workspace, /Nothing is preselected/);
  assert.match(workspace, />Shortlist</);
  assert.match(workspace, /Do Not Shortlist/);
  assert.match(workspace, /Undecided/);
});

test("proposal selection is restricted to shortlisted decisions", () => {
  assert.match(workspace, /filter\(\(item\) => item\.state === "shortlisted"\)/);
  assert.match(workspace, /Choose one Shortlisted bid/);
  assert.match(workspace, /No Acceptable Bid/);
});

test("finalization displays blockers, requires confirmation and becomes read only", () => {
  assert.match(workspace, /review\.blockers/);
  assert.match(workspace, /window\.confirm/);
  assert.match(workspace, /FinalizedReview/);
  assert.match(workspace, /Finalized by/);
  assert.match(workspace, /corrections require a successor review/);
});

test("human review API is comparison scoped and exposes no award action", () => {
  assert.match(api, /bid-comparisons\/\$\{comparisonId\}\/human-reviews/);
  assert.match(api, /updateDecision/);
  assert.match(api, /finalize/);
  assert.doesNotMatch(api, /winner|awarded|recommendation/i);
});

test("ready comparison retains evidence and adds the separate human review", () => {
  assert.match(comparison, /Source page/);
  assert.match(comparison, /source\.excerpt/);
  assert.match(comparison, /HumanBidReview/);
  assert.match(comparison, /make a procurement decision/);
});
