import assert from "node:assert/strict";
import test from "node:test";
import { projectPortfolioCounts, projectStatusTone } from "./project-list-presentation.ts";

test("project summary derives active and archived counts from production records", () => {
  assert.deepEqual(projectPortfolioCounts([
    { is_active: true },
    { is_active: false },
    { is_active: false },
  ]), { total: 3, active: 1, archived: 2 });
});

test("project status presentation clearly distinguishes workflow and archive state", () => {
  assert.equal(projectStatusTone("human_scope_review"), "amber");
  assert.equal(projectStatusTone("ai_analysis"), "purple");
  assert.equal(projectStatusTone("awarded"), "green");
  assert.equal(projectStatusTone("human_scope_review", true), "slate");
});
