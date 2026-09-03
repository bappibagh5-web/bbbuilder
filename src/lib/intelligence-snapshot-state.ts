import type { IntelligenceReadiness, IntelligenceSnapshot } from "./analysis.ts";

export function snapshotActions(canOperate: boolean, readiness: IntelligenceReadiness | null) {
  return {
    canCreate: canOperate && Boolean(readiness?.eligible),
    canApprove: (snapshot: IntelligenceSnapshot) =>
      canOperate && !snapshot.approval && !snapshot.is_stale,
  };
}

export function snapshotStatus(snapshot: IntelligenceSnapshot) {
  if (snapshot.approval) return snapshot.is_stale ? "approved_historical" : "approved";
  return snapshot.is_stale ? "stale" : "awaiting_approval";
}

export function selectedRunsRespectRevisionBoundary(
  selectedIds: number[],
  candidates: { id: number; document_revision_id: number }[],
) {
  const selected = candidates.filter((candidate) => selectedIds.includes(candidate.id));
  return new Set(selected.map((candidate) => candidate.document_revision_id)).size === selected.length;
}
