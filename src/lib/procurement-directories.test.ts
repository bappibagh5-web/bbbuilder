import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const campaignsPage = readFileSync("src/app/(app)/campaigns/page.tsx", "utf8");
const comparisonsPage = readFileSync("src/app/(app)/comparisons/page.tsx", "utf8");
const proposalsPage = readFileSync("src/app/(app)/proposals/page.tsx", "utf8");
const campaigns = readFileSync("src/components/campaigns/campaign-directory.tsx", "utf8");
const comparisons = readFileSync("src/components/comparisons/comparison-directory.tsx", "utf8");
const proposals = readFileSync("src/components/proposals/proposal-directory.tsx", "utf8");

test("global procurement routes use organization APIs without demo fixtures", () => {
  for (const page of [campaignsPage, comparisonsPage, proposalsPage]) assert.doesNotMatch(page, /@\/data/);
  for (const component of [campaigns, comparisons, proposals]) {
    assert.doesNotMatch(component, /Demo environment|simulated/);
    assert.match(component, /procurementDirectoriesApi\./);
  }
});

test("campaigns expose bounded real counts and exact project outreach link", () => {
  assert.match(campaigns, /Loading outreach campaigns/);
  assert.match(campaigns, /Campaigns unavailable/);
  assert.match(campaigns, /No outreach campaigns yet/);
  assert.match(campaigns, /item\.invited_count/);
  assert.match(campaigns, /item\.delivered_count/);
  assert.match(campaigns, /item\.responded_count/);
  assert.match(campaigns, /href=\{item\.project_url\}/);
  assert.doesNotMatch(campaigns, /message\.body|attachments|replies/);
});

test("comparisons never infer a winner recommendation or cheapest bid", () => {
  assert.match(comparisons, /No bidder is ranked or recommended here/);
  assert.match(comparisons, /selected_for_proposal/);
  assert.match(comparisons, /No finalized selection/);
  assert.match(comparisons, /href=\{item\.project_url\}/);
  assert.doesNotMatch(comparisons, /cheapest|priceRange|recommendation/);
});

test("proposals render client-facing totals without internal procurement leakage", () => {
  assert.match(proposals, /Loading client proposals/);
  assert.match(proposals, /Proposals unavailable/);
  assert.match(proposals, /No client proposals yet/);
  assert.match(proposals, /item\.proposed_amount/);
  assert.match(proposals, /item\.pdf_available/);
  assert.match(proposals, /item\.award_status/);
  assert.match(proposals, /Issue Date/);
  assert.match(proposals, /item\.issue_date/);
  assert.doesNotMatch(proposals, /contractor.*base.*bid|leveling|markup.rate|procurement.*id/i);
});

test("all global procurement directories remain read only for every membership role", () => {
  for (const component of [campaigns, comparisons, proposals]) {
    assert.match(component, /useOrganization/);
    assert.doesNotMatch(component, /method:\s*["'](?:POST|PATCH|PUT|DELETE)/);
    assert.doesNotMatch(component, /Create Campaign|>Finalize<|Award Contractor/);
  }
});
