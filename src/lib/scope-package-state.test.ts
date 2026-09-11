import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ScopePackage } from "./scope-packages.ts";
import {
  itemsToLines,
  linesToItems,
  replaceScopePackage,
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
  assert.match(source, /scopeItem\.sources\.map/);
  assert.match(source, /source\.page_number/);
});

test("scope editor converts one inclusion per non-empty line", () => {
  assert.deepEqual(linesToItems("First\n\n Second \r\nThird"), ["First", "Second", "Third"]);
  assert.equal(itemsToLines(["First", "Second"]), "First\nSecond");
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
