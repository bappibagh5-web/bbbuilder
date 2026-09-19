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
  assert.match(moduleSource, /Pricing calculations, selected-bid assembly, PDF generation, finalization, and awards are intentionally not active yet/);
});

test("frontend binds proposal creation to an exact estimate version", () => {
  assert.match(api, /estimate_version_id: estimateVersionId/);
  assert.match(moduleSource, /Bound to Estimate V/);
  assert.match(moduleSource, /Version history/);
});

test("viewer receives no creation controls from backend authority", () => {
  assert.match(moduleSource, /workspace\.can_edit && !workspace\.estimate/);
  assert.match(moduleSource, /workspace\.can_edit && estimateVersion/);
});
