import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const api = readFileSync("src/lib/proposals.ts", "utf8");
const moduleSource = readFileSync("src/components/proposals/production-proposal-workspace.tsx", "utf8");
const workspace = readFileSync("src/components/projects/production-project-workspace.tsx", "utf8");

test("numeric Proposal tab uses the production M4 workspace", () => {
  assert.match(workspace, /section === "proposal"/);
  assert.match(workspace, /ProductionProposalWorkspace/);
});

test("proposal workspace exposes honest draft-only language and explicit creation", () => {
  assert.match(moduleSource, /Start proposal preparation/);
  assert.match(moduleSource, /Create Draft proposal/);
  assert.match(moduleSource, /Draft preparation only/);
  assert.match(moduleSource, /Build a traceable internal estimate with deterministic arithmetic/);
  assert.match(moduleSource, /No AI arithmetic, PDF generation, final approval, award/);
});

test("frontend binds proposal creation to an exact estimate version", () => {
  assert.match(api, /estimate_version_id: estimateVersionId/);
  assert.match(moduleSource, /Bound permanently to Estimate V/);
  assert.match(moduleSource, /Version history/);
});

test("viewer receives no creation controls from backend authority", () => {
  assert.match(moduleSource, /workspace\.can_edit && !workspace\.estimate/);
  assert.match(moduleSource, /workspace\.can_edit && estimateVersion/);
  assert.match(moduleSource, /canEdit && <CommercialActions/);
});

test("selected bid assembly is explicit and visible only to authorized users", () => {
  assert.match(moduleSource, /Selected bids ready to assemble/);
  assert.match(moduleSource, /Assemble selected bid/);
  assert.match(moduleSource, /canEdit && available\.length/);
  assert.doesNotMatch(moduleSource, /useEffect[\s\S]{0,300}\.assemble\(/);
});

test("contractor quote and BB leveling remain distinct", () => {
  assert.match(moduleSource, /Contractor quote/);
  assert.match(moduleSource, /BB comparison leveling/);
  assert.match(moduleSource, /Ready BidRevision #/);
  assert.match(moduleSource, /ScopeVersion #/);
});

test("financial summary is backend-derived and omits unknown values", () => {
  assert.match(moduleSource, /Calculated Estimate Amount/);
  assert.match(moduleSource, /item\[1\] !== null/);
  assert.match(moduleSource, /not a finalized client proposal price/);
  assert.doesNotMatch(moduleSource, /parseFloat|Number\(.*amount/);
});

test("commercial actions are explicit and later milestones stay unavailable", () => {
  assert.match(moduleSource, /Add allowance/);
  assert.match(moduleSource, /Add alternate \/ option/);
  assert.match(moduleSource, /Add exclusion/);
  assert.match(moduleSource, /Add commercial adjustment/);
  assert.match(moduleSource, /No AI arithmetic, PDF generation, final approval, award/);
  assert.match(moduleSource, /type="number" min="0" step="0\.01"/);
  assert.match(moduleSource, /step="0\.000001"/);
  assert.doesNotMatch(moduleSource, /recommend(ed|ation)|winner/i);
});

test("Draft commercial records expose pre-populated in-place editing", () => {
  assert.match(api, /updateCommercial/);
  assert.match(api, /method: "PATCH"/);
  assert.match(api, /\$\{kind\}\/\$\{itemId\}\//);
  assert.match(moduleSource, /title={`Edit \$\{row\.form\}`}/);
  assert.match(moduleSource, /defaultValue={initial\?\.description/);
  assert.match(moduleSource, /defaultChecked={initial\?\.included/);
  assert.match(moduleSource, /canEdit && <div className="mt-2">/);
  assert.doesNotMatch(moduleSource, /deleteCommercial|method: "DELETE"/);
});

test("ProposalVersion retains exact EstimateVersion binding", () => {
  assert.match(api, /bound_proposal_estimate/);
  assert.match(moduleSource, /Bound permanently to Estimate V/);
  assert.doesNotMatch(moduleSource, /latest estimate/i);
});
