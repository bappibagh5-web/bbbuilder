import assert from "node:assert/strict";
import test from "node:test";
import {
  itemsToLines,
  linesToItems,
  replaceScopePackage,
  scopePackageCounts,
} from "./scope-package-state.ts";

test("scope package counts distinguish draft and human-ready state", () => {
  const packages = ["draft", "ready", "draft"].map((status) => ({
    current_version: { status },
  })) as Parameters<typeof scopePackageCounts>[0];
  assert.deepEqual(scopePackageCounts(packages), { total: 3, ready: 1, draft: 2 });
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
