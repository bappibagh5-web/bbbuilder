import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const api = readFileSync("src/lib/proposals.ts", "utf8");
const moduleSource = readFileSync("src/components/proposals/production-proposal-workspace.tsx", "utf8");
const workspace = readFileSync("src/components/projects/production-project-workspace.tsx", "utf8");
const awardedPage = readFileSync("src/app/(app)/awarded/page.tsx", "utf8");
const awardedDirectory = readFileSync("src/components/awarded/awarded-directory.tsx", "utf8");

test("numeric Proposal tab uses the production M4 workspace", () => {
  assert.match(workspace, /section === "proposal"/);
  assert.match(workspace, /ProductionProposalWorkspace/);
});

test("proposal workspace exposes controlled creation and finalization language", () => {
  assert.match(moduleSource, /Start proposal preparation/);
  assert.match(moduleSource, /Create Draft proposal/);
  assert.match(moduleSource, /Draft preparation only/);
  assert.match(moduleSource, /Build a traceable internal estimate with deterministic arithmetic/);
  assert.match(moduleSource, /Finalization freezes the exact proposal and estimate/);
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

test("commercial actions are explicit and award actions stay unavailable", () => {
  assert.match(moduleSource, /Add allowance/);
  assert.match(moduleSource, /Add alternate \/ option/);
  assert.match(moduleSource, /Add exclusion/);
  assert.match(moduleSource, /Add commercial adjustment/);
  assert.match(moduleSource, /not client acceptance, an award, subcontract, or purchase order/);
  assert.match(moduleSource, /type="number" min="0" step="0\.01"/);
  assert.match(moduleSource, /step="0\.000001"/);
  assert.doesNotMatch(moduleSource, /recommend(ed|ation)|winner/i);
});

test("client proposal preview is separate and never calculates money in JavaScript", () => {
  assert.match(moduleSource, /Draft client proposal/);
  assert.match(moduleSource, /Client-facing preview/);
  assert.match(moduleSource, /Internal contractor pricing, leveling, and adjustment rates are intentionally omitted/);
  assert.match(moduleSource, /Proposed Contract Amount/);
  assert.doesNotMatch(moduleSource, /parseFloat|Number\(.*calculated/);
});

test("finalization and PDF actions use backend-authoritative APIs", () => {
  assert.match(api, /finalizeProposal/);
  assert.match(api, /generatePdf/);
  assert.match(api, /proposal-pdfs\/\$\{artifactId\}\/download/);
  assert.match(api, /apiResponse/);
  assert.match(moduleSource, /Finalize proposal/);
  assert.match(moduleSource, /Generate final PDF/);
  assert.match(moduleSource, /Generate corrected PDF/);
  assert.match(moduleSource, /pdf_update_available/);
  assert.match(moduleSource, /Download final PDF/);
  assert.match(moduleSource, /window\.confirm/);
  assert.match(moduleSource, /This proposal has not been awarded or accepted/);
  assert.match(moduleSource, /reason instanceof Error \? reason\.message/);
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

test("proposal refresh tolerates an older workspace payload during service reload", () => {
  assert.match(moduleSource, /current_version \?\? workspace\.proposal!\.versions\.at\(-1\)/);
  assert.match(moduleSource, /client_contacts \?\?= \[\]/);
  assert.match(moduleSource, /if \(!currentVersion\) return null/);
});

test("award decisions remain explicit human actions after proposal finalization", () => {
  assert.match(moduleSource, /workspace\.awards \?\?/);
  assert.match(moduleSource, /project_awards: \[\]/);
  assert.match(moduleSource, /trade_awards: \[\]/);
  assert.match(moduleSource, /eligible_trade_awards: \[\]/);
  assert.match(moduleSource, /Proposal finalized — awaiting client award\/acceptance/);
  assert.match(moduleSource, /Record Client Award \/ Acceptance/);
  assert.match(moduleSource, /Confirm Client Award/);
  assert.match(moduleSource, /Record Subcontractor Award/);
  assert.match(moduleSource, /Confirm Subcontractor Award/);
  assert.match(moduleSource, /window\.confirm\("Confirm this client award as an immutable human decision\?"/);
  assert.match(moduleSource, /workspace\.can_edit && latest\.status === "draft"/);
  assert.doesNotMatch(moduleSource, /useEffect[\s\S]{0,300}(createProjectAward|confirmProjectAward|createTradeAward|confirmTradeAward)/);
});

test("quoted evaluated and awarded trade values stay visibly distinct", () => {
  assert.match(moduleSource, />Quoted</);
  assert.match(moduleSource, />Evaluated internally</);
  assert.match(moduleSource, />Awarded</);
  assert.match(moduleSource, /Explicit award amount/);
  assert.match(moduleSource, /no notification or subcontract was sent/);
});

test("awarded transition and M5 handoff are explicit and do not run external sync", () => {
  assert.match(moduleSource, /Transition Project to Awarded/);
  assert.match(moduleSource, /create an immutable M5-ready handoff snapshot/);
  assert.match(moduleSource, /No external synchronization has run/);
  assert.match(api, /transitionAwarded/);
  assert.doesNotMatch(api, /createSubcontract|createPurchaseOrder|syncAward/);
});

test("Awarded Projects uses the production award read model", () => {
  assert.match(awardedPage, /AwardedDirectory/);
  assert.match(awardedDirectory, /awardedProjects/);
  assert.match(awardedDirectory, /client awards/i);
  assert.match(awardedDirectory, /Proposal/);
  assert.match(awardedDirectory, /Procurement history/);
});
