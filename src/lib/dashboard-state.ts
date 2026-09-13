export function dashboardAttentionDescription(item: {
  project_review: { current: boolean } | null;
  review: { total: number; complete: boolean; needs_attention: number; conflicts: number };
  active_document_count: number;
  reviewed_document_count: number;
}) {
  const parts: string[] = [];
  if (item.project_review) {
    if (!item.project_review.current) parts.push("Estimating set changed since review");
    else if (!item.review.complete && !item.review.needs_attention && !item.review.conflicts) parts.push("Project review not complete");
  } else {
    const incomplete = item.active_document_count - item.reviewed_document_count;
    if (incomplete > 0) parts.push(`${incomplete} current document${incomplete === 1 ? "" : "s"} not fully reviewed`);
  }
  if (item.review.needs_attention) parts.push(`${item.review.needs_attention} finding${item.review.needs_attention === 1 ? "" : "s"} ${item.review.needs_attention === 1 ? "needs" : "need"} follow-up`);
  if (item.review.conflicts) parts.push(`${item.review.conflicts} open conflict${item.review.conflicts === 1 ? "" : "s"}`);
  return parts.join(" · ");
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
