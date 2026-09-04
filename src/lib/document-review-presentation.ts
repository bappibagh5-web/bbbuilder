import type {
  AnalysisRun,
  ExtractedFinding,
  FindingDecision,
  IntelligenceSnapshot,
} from "./analysis.ts";

export type ReviewStageState = "completed" | "current" | "upcoming" | "blocked";

export type ReviewStage = {
  key: "uploaded" | "prepared" | "ai_reviewed" | "your_review" | "approved";
  label: string;
  detail: string;
  state: ReviewStageState;
};

export const categoryPresentation: Record<string, string> = {
  project_fact: "Project Details",
  date_deadline: "Important Dates",
  bid_condition: "Commercial Conditions",
  scope_trade: "Scope Requirements",
  responsibility: "Responsibilities",
  permit_inspection: "Permits & Inspections",
  landlord_requirement: "Landlord / Owner Requirements",
  owner_third_party_item: "Landlord / Owner Requirements",
  commercial: "Commercial Conditions",
  submittal_closeout: "Submittal / Closeout Requirements",
  open_question: "Questions to Follow Up",
};

export const decisionPresentation: Record<ExtractedFinding["review_status"], string> = {
  unreviewed: "Needs your review",
  accepted: "Confirmed",
  edited_accepted: "Confirmed",
  rejected: "Not relevant",
  needs_clarification: "Needs follow-up",
};

export const documentReviewScopeCopy = {
  selectedDocument: "This section shows what AI found in the selected document.",
  projectWideHeading: "Project Information for Approval",
  projectWideBadge: "Project-wide",
  projectWideExplanation: "Reviewed information from your current project documents is combined here before final approval.",
} as const;

export function categoryLabel(category: string) {
  return categoryPresentation[category] ?? "Project Details";
}

export function decisionLabel(decision: ExtractedFinding["review_status"] | FindingDecision) {
  return decisionPresentation[decision];
}

export function documentVersionLabel(isCurrent: boolean, revisionLabel: string, revisionId: number) {
  const label = revisionLabel || `Revision ${revisionId}`;
  return isCurrent ? `Current Version (${label})` : `Older Document Version (${label})`;
}

export function reviewCounts(findings: Pick<ExtractedFinding, "review_status">[]) {
  const confirmed = findings.filter((item) => item.review_status === "accepted" || item.review_status === "edited_accepted").length;
  const notRelevant = findings.filter((item) => item.review_status === "rejected").length;
  const followUp = findings.filter((item) => item.review_status === "needs_clarification").length;
  const unreviewed = findings.filter((item) => item.review_status === "unreviewed").length;
  return {
    total: findings.length,
    reviewed: confirmed + notRelevant + followUp,
    confirmed,
    notRelevant,
    followUp,
    unreviewed,
    needsAttention: followUp + unreviewed,
    complete: findings.length > 0 && followUp === 0 && unreviewed === 0,
  };
}

export function progressPresentation(analysisStarted: boolean, counts: ReturnType<typeof reviewCounts>) {
  if (!analysisStarted && counts.total === 0) {
    return {
      heading: "Not reviewed yet",
      detail: "AI review has not been started for this document.",
      nextStep: "Review this document with AI.",
    };
  }
  return {
    heading: `${counts.reviewed} / ${counts.total}`,
    detail: "items reviewed",
    nextStep: counts.complete
      ? "Prepare the reviewed project information for approval."
      : "Review the remaining items, then prepare the project information for approval.",
  };
}

export function versionSummary(snapshot: IntelligenceSnapshot) {
  const entries = snapshot.sources.flatMap((source) => source.entries);
  return {
    included: entries.filter((entry) => entry.included_in_intelligence).length,
    notRelevant: entries.filter((entry) => !entry.included_in_intelligence).length,
    sources: snapshot.sources.map((source) => `${source.document_title} — ${source.revision_label || `Version ${source.document_revision}`}`),
  };
}

export const versionDetailsInitiallyExpanded = false;

export function versionDetailsButtonLabel(expanded: boolean) {
  return expanded ? "Hide version details" : "View version details";
}

export function plainAnalysisStatus(status: AnalysisRun["status"] | undefined) {
  if (status === "queued") return "AI review is waiting to begin";
  if (status === "running") return "AI is reviewing your document";
  if (status === "succeeded") return "Document review complete";
  if (status === "failed") return "We couldn't finish reviewing this document";
  return "Ready for AI review";
}

export function snapshotPresentation(snapshot: IntelligenceSnapshot) {
  if (snapshot.approval) return snapshot.is_stale ? "Approved earlier version" : "Approved";
  return snapshot.is_stale ? "Update required" : "Ready for approval";
}

export function reviewStages(input: {
  uploaded: boolean;
  sourceStatus?: string;
  pdfStatus?: string;
  pageCount: number;
  runStatus?: AnalysisRun["status"];
  findingCount: number;
  needsAttention: number;
  approved: boolean;
}): ReviewStage[] {
  const prepared = input.sourceStatus === "succeeded" && input.pdfStatus === "succeeded" && input.pageCount > 0;
  const reviewedByAi = input.runStatus === "succeeded";
  const humanComplete = input.findingCount > 0 && input.needsAttention === 0;
  const failed = input.sourceStatus === "failed" || input.pdfStatus === "failed" || input.runStatus === "failed";
  const currentKey = !input.uploaded ? "uploaded" : !prepared ? "prepared" : !reviewedByAi ? "ai_reviewed" : !humanComplete ? "your_review" : "approved";
  const order = ["uploaded", "prepared", "ai_reviewed", "your_review", "approved"] as const;
  const currentIndex = order.indexOf(currentKey);
  const details = {
    uploaded: "File uploaded securely",
    prepared: prepared ? `${input.pageCount} pages checked and organized` : "Checking file and organizing pages",
    ai_reviewed: reviewedByAi ? "AI found relevant information" : "AI reviews project requirements",
    your_review: humanComplete ? "All items confirmed or excluded" : "Confirm, edit or exclude items",
    approved: input.approved ? "Approved project information saved" : "Save as approved project information",
  };
  const labels = { uploaded: "Uploaded", prepared: "Prepared", ai_reviewed: "AI Reviewed", your_review: "Your Review", approved: "Approved" };
  return order.map((key, index) => ({
    key,
    label: labels[key],
    detail: details[key],
    state: input.approved || index < currentIndex ? "completed" : failed && index === currentIndex ? "blocked" : index === currentIndex ? "current" : "upcoming",
  }));
}
