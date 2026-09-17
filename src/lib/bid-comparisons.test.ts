import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workspace = readFileSync("src/components/comparisons/production-bid-comparisons.tsx", "utf8");
const shell = readFileSync("src/components/projects/production-project-workspace.tsx", "utf8");
const api = readFileSync("src/lib/bid-comparisons.ts", "utf8");

test("numeric production projects use the real comparison workspace", () => {
  assert.match(shell, /section === "comparisons"/);
  assert.match(shell, /ProductionBidComparisons/);
  assert.match(api, /bid-comparisons/);
});

test("bid revision selection is explicit and never preselects latest or cheapest", () => {
  assert.match(workspace, /Nothing is preselected/);
  assert.match(workspace, /Add this revision/);
  assert.doesNotMatch(workspace, /recommended bidder|select winner|best bid/i);
});

test("commercial values remain separate from explicit deterministic adjustments", () => {
  assert.match(workspace, /Submitted Base Bid/);
  assert.match(workspace, /Commercial terms/);
  assert.match(workspace, /ADD/);
  assert.match(workspace, /DEDUCT/);
  assert.match(workspace, /never rewrite contractor pricing/i);
});

test("scope matrix preserves missing coverage as not addressed", () => {
  assert.match(workspace, /Scope leveling matrix/);
  assert.match(workspace, /Not addressed/);
  assert.match(workspace, /not assumed excluded/);
});

test("ready is a human review gate and not an award", () => {
  assert.match(workspace, /Mark Ready for Human Review/);
  assert.match(workspace, /separate human review records the procurement decision/i);
});

test("grounded condition detail and evidence remain visible", () => {
  assert.match(workspace, /item\.kind === "condition"/);
  assert.match(workspace, /item\.detail/);
  assert.match(workspace, /Source page/);
  assert.match(workspace, /source\.excerpt/);
});
