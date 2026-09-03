import assert from "node:assert/strict";
import test from "node:test";
import type { IntelligenceSnapshot } from "./analysis.ts";
import {
  selectedRunsRespectRevisionBoundary,
  snapshotActions,
  snapshotStatus,
} from "./intelligence-snapshot-state.ts";

const snapshot = (overrides: Partial<IntelligenceSnapshot> = {}): IntelligenceSnapshot => ({
  id: 1, project: 2, version: 1, fingerprint: "a".repeat(64), schema_version: "v1",
  summary_counts: { approved_entries: 2 }, created_by: "admin@example.com",
  created_at: "2026-09-03T00:00:00Z", sources: [], approval: null, is_stale: false,
  ...overrides,
});

test("eligible operator can create and approve exact current snapshot", () => {
  const actions = snapshotActions(true, { eligible: true, blockers: [], fingerprint: "x", summary_counts: {} });
  assert.equal(actions.canCreate, true);
  assert.equal(actions.canApprove(snapshot()), true);
});

test("blockers and Viewer access suppress all mutation actions", () => {
  const blocked = snapshotActions(true, { eligible: false, blockers: [{ code: "unreviewed", message: "Blocked", count: 1 }], fingerprint: "", summary_counts: {} });
  assert.equal(blocked.canCreate, false);
  const viewer = snapshotActions(false, { eligible: true, blockers: [], fingerprint: "x", summary_counts: {} });
  assert.equal(viewer.canCreate, false);
  assert.equal(viewer.canApprove(snapshot()), false);
});

test("stale or approved snapshots cannot expose approval action", () => {
  const actions = snapshotActions(true, null);
  assert.equal(actions.canApprove(snapshot({ is_stale: true })), false);
  assert.equal(actions.canApprove(snapshot({ approval: { id: 1, project: 2, snapshot: 1, approver: "a", approved_at: "now", approval_note: "", readiness_result: {} } })), false);
  assert.equal(snapshotStatus(snapshot({ is_stale: true })), "stale");
  assert.equal(snapshotStatus(snapshot({ approval: { id: 1, project: 2, snapshot: 1, approver: "a", approved_at: "now", approval_note: "", readiness_result: {} }, is_stale: true })), "approved_historical");
});

test("two runs for one revision cannot be selected together", () => {
  const candidates = [{ id: 3, document_revision_id: 7 }, { id: 4, document_revision_id: 7 }, { id: 5, document_revision_id: 8 }];
  assert.equal(selectedRunsRespectRevisionBoundary([3, 5], candidates), true);
  assert.equal(selectedRunsRespectRevisionBoundary([3, 4], candidates), false);
});
