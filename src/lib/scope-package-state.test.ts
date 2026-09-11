import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ScopePackage } from "./scope-packages.ts";
import {
  itemsToLines,
  itemTypeLabel,
  linesToItems,
  replaceScopePackage,
  responsibilityLabel,
  scopePackageCounts,
  scopeItemCount,
  scopePackageGenerations,
} from "./scope-package-state.ts";

test("scope package counts distinguish draft and human-ready state", () => {
  const packages = ["draft", "ready", "draft"].map((status) => ({
    current_version: { status },
  })) as Parameters<typeof scopePackageCounts>[0];
  assert.deepEqual(scopePackageCounts(packages), { total: 3, ready: 1, draft: 2 });
});

test("scope item count totals the current detailed generation", () => {
  const packages = [2, 5, 1].map((count) => ({
    current_version: { scope_items: Array.from({ length: count }, (_, id) => ({ id })) },
  })) as Parameters<typeof scopeItemCount>[0];
  assert.equal(scopeItemCount(packages), 8);
});

test("current generation is separated from preserved superseded history", () => {
  const packages = [
    { id: 1, lifecycle: "superseded" },
    { id: 2, lifecycle: "active" },
    { id: 3, lifecycle: "superseded" },
  ] as ScopePackage[];
  const result = scopePackageGenerations(packages);
  assert.deepEqual(result.active.map((item) => item.id), [2]);
  assert.deepEqual(result.historical.map((item) => item.id), [1, 3]);
});

test("Scopes UI exposes item counts, expandable provenance, and generation history", () => {
  const source = readFileSync(
    new URL("../components/scopes/production-scopes-module.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /Current trade packages/);
  assert.match(source, /Detailed scope items/);
  assert.match(source, /View generation history/);
  assert.match(source, /ScopeItemSources sources=\{scopeItem\.sources\}/);
  assert.match(source, /source\.page_number/);
});

test("Scopes UI offers an explicit read-only coverage preview with provenance", () => {
  const source = readFileSync(
    new URL("../components/scopes/production-scopes-module.tsx", import.meta.url),
    "utf8",
  );
  const api = readFileSync(new URL("./scope-packages.ts", import.meta.url), "utf8");
  assert.match(source, /Preview New Scope Coverage/);
  assert.match(source, /Previewing does not create or supersede scope records/);
  assert.match(source, /New scope coverage from Project Information/);
  assert.match(source, /Trade scopes identified/);
  assert.match(source, /Project-wide requirements/);
  assert.match(source, /responsibilityLabel\(scopeItem\.responsibility\)/);
  assert.match(source, /Responsibility not stated/);
  assert.match(source, /preview\.total_requirement_count/);
  assert.match(source, /Supporting sources:/);
  assert.match(source, /Show all {sources\.length} sources/);
  assert.match(source, /Scope coverage check/);
  assert.match(source, /Limited evidence/);
  assert.match(source, /does not guarantee that the trade is unnecessary/);
  assert.match(source, /Advanced details/);
  assert.match(source, /bundled_findings_split/);
  assert.match(source, /passive_fire_items_removed_from_sprinklers/);
  assert.match(source, /preview\.packages\.map/);
  assert.match(source, /source\.document_revision_id/);
  assert.match(source, /source\.page_number/);
  assert.match(api, /scope-coverage-preview/);
  assert.doesNotMatch(api, /scope-coverage-preview[\s\S]{0,200}method:\s*"POST"/);
});

test("scope generation requires the accepted preview and plain-language confirmation", () => {
  const source = readFileSync(
    new URL("../components/scopes/production-scopes-module.tsx", import.meta.url),
    "utf8",
  );
  const api = readFileSync(new URL("./scope-packages.ts", import.meta.url), "utf8");
  assert.match(source, /Create a new draft scope generation from Project Information V/);
  assert.match(source, /Project-wide requirements kept separate/);
  assert.match(source, /Every new trade scope will start as Draft/);
  assert.match(source, /Contractor discovery will not use these scopes/);
  assert.match(source, /Create Draft Scopes/);
  assert.match(api, /expected_plan_fingerprint: preview\.plan_fingerprint/);
  assert.match(api, /expected_project_information_version/);
  assert.match(api, /confirmed: true/);
  assert.doesNotMatch(api, /snapshot_id: snapshotId/);
});

test("scope editor converts one inclusion per non-empty line", () => {
  assert.deepEqual(linesToItems("First\n\n Second \r\nThird"), ["First", "Second", "Third"]);
  assert.equal(itemsToLines(["First", "Second"]), "First\nSecond");
});

test("scope responsibility codes use client-facing business language", () => {
  assert.equal(responsibilityLabel("unclear"), "Responsibility not stated in documents");
  assert.equal(responsibilityLabel("supply_install"), "Supply & install");
  assert.equal(responsibilityLabel("relocate_reuse"), "Relocate / reuse");
  assert.equal(responsibilityLabel("install_only"), "Install only");
  assert.equal(itemTypeLabel("supply_install"), "Supply Install");
});

test("generated package presentation separates work and confirmation needs", () => {
  const source = readFileSync(
    new URL("../components/scopes/production-scopes-module.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /title="Work Included"/);
  assert.match(source, /title="Needs Confirmation"/);
  assert.match(source, /title="Exclusions"/);
  assert.match(source, /title="Notes"/);
  assert.match(source, /scopeItem\.responsibility === "unclear"/);
  assert.match(source, /Supporting sources: \{sources\.length\}/);
  assert.match(source, /Show all \{sources\.length\} sources/);
  assert.doesNotMatch(source, /scopeItem\.responsibility\.replaceAll/);
});

test("successful Ready response replaces the package immediately", () => {
  const draft = { id: 1, current_version: { status: "draft" } };
  const other = { id: 2, current_version: { status: "draft" } };
  const ready = { id: 1, current_version: { status: "ready" } };
  const result = replaceScopePackage(
    [draft, other] as Parameters<typeof replaceScopePackage>[0],
    ready as Parameters<typeof replaceScopePackage>[1],
  );
  assert.equal(result[0], ready);
  assert.equal(result[1], other);
  assert.deepEqual(scopePackageCounts(result), { total: 2, ready: 1, draft: 1 });
});
