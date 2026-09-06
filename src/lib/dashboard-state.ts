import type { ExtractedFinding, IntelligenceConflict } from "./analysis.ts";

export type DashboardReviewCounts = {
  total: number;
  aiHandled: number;
  reviewedByUser: number;
  needsAttention: number;
  conflicts: number;
  complete: boolean;
};

export function dashboardReviewCounts(
  findings: Pick<ExtractedFinding, "handling_status">[],
  conflicts: Pick<IntelligenceConflict, "status">[],
): DashboardReviewCounts {
  const openConflicts = conflicts.filter((conflict) => conflict.status === "open").length;
  const aiHandled = findings.filter((finding) => finding.handling_status === "ai_handled").length;
  const reviewedByUser = findings.filter((finding) =>
    finding.handling_status.startsWith("human_"),
  ).length;
  const needsAttention = findings.filter((finding) =>
    ["needs_attention", "human_needs_follow_up"].includes(finding.handling_status),
  ).length;
  return {
    total: findings.length,
    aiHandled,
    reviewedByUser,
    needsAttention,
    conflicts: openConflicts,
    complete: findings.length > 0 && needsAttention === 0 && openConflicts === 0,
  };
}

export function projectNeedsAttention(input: {
  activeDocumentCount: number;
  reviewedDocumentCount: number;
  needsAttention: number;
  conflicts: number;
}) {
  return (
    input.activeDocumentCount === 0 ||
    input.needsAttention > 0 ||
    input.conflicts > 0 ||
    input.activeDocumentCount > input.reviewedDocumentCount
  );
}

export const dashboardActivityLabels: Record<string, string> = {
  "project.created": "Project created",
  "project.updated": "Project details updated",
  "project.status_changed": "Project stage updated",
  "file.uploaded": "Project file uploaded",
  "document.created": "Document created",
  "document_revision.created": "Document version added",
  "document.current_revision_changed": "Current document version updated",
  "document.archived": "Document archived",
  "document.reactivated": "Document restored",
  "analysis.requested": "AI document review started",
  "analysis.completed": "AI document review completed",
  "findings.materialized": "Document findings prepared",
  "finding.accepted": "Project item confirmed",
  "finding.edited": "Project item edited and confirmed",
  "finding.rejected": "Project item marked not relevant",
  "finding.needs_clarification": "Project item needs follow-up",
  "intelligence_snapshot.created": "Project information version prepared",
  "intelligence_snapshot.approved": "Project information approved",
};

export function dashboardActivityLabel(actionCode: string) {
  return dashboardActivityLabels[actionCode] ?? actionCode.replaceAll("_", " ").replaceAll(".", " · ");
}
