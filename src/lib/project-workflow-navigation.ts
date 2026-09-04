export const projectWorkflowNavigation = [
  { label: "Overview", slug: "" },
  { label: "Documents", slug: "documents" },
  { label: "Document Review", slug: "ai-review", badge: "AI-assisted" },
  { label: "Scopes", slug: "scopes" },
  { label: "Contractors", slug: "contractors" },
  { label: "Outreach", slug: "outreach" },
  { label: "Bids", slug: "bids" },
  { label: "Comparisons", slug: "comparisons" },
  { label: "Proposal", slug: "proposal" },
  { label: "Activity", slug: "activity" },
] as const;

export function projectWorkflowHref(projectId: string, slug: string) {
  const base = `/projects/${projectId}`;
  return slug ? `${base}/${slug}` : base;
}
