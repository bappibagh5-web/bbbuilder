import type { ActivityEvent, AttentionItem } from "@/types";
export const dashboardMetrics = [
  {
    label: "Active Projects",
    value: "5",
    detail: "Current preconstruction pipeline",
    tone: "positive" as const,
  },
  {
    label: "Awaiting Review",
    value: "5",
    detail: "Human action required",
    tone: "warning" as const,
  },
  {
    label: "Bid Submissions",
    value: "94",
    detail: "Across active projects",
    tone: "neutral" as const,
  },
  {
    label: "Client Proposals",
    value: "19",
    detail: "Across all proposal stages",
    tone: "positive" as const,
  },
];
export const attentionItems: AttentionItem[] = [
  {
    id: "att-1",
    projectName: "Retail Store Tenant Improvement",
    message: "Client proposal is ready for final approval",
    severity: "critical",
  },
  {
    id: "att-2",
    projectName: "Fashion Retail Fit-Out",
    message: "3 AI-assisted trade scopes require review",
    severity: "ai",
  },
  {
    id: "att-3",
    projectName: "Restaurant Tenant Improvement",
    message: "7 subcontractors have not responded",
    severity: "warning",
  },
  {
    id: "att-4",
    projectName: "Commercial Office Renovation",
    message: "AI-assisted document review is ready",
    severity: "info",
  },
];
export const recentActivity: ActivityEvent[] = [
  {
    id: "act-1",
    type: "bid",
    title: "Bid received from Demo Pacific Electrical Ltd.",
    projectName: "Retail Store Tenant Improvement",
    createdAt: "2026-08-23T11:50:00Z",
  },
  {
    id: "act-2",
    type: "ai",
    title: "AI-assisted document review completed",
    projectName: "Commercial Office Renovation",
    createdAt: "2026-08-23T11:28:00Z",
  },
  {
    id: "act-3",
    type: "scope",
    title: "Trade scope approved: HVAC",
    projectName: "Fashion Retail Fit-Out",
    createdAt: "2026-08-23T11:00:00Z",
  },
  {
    id: "act-4",
    type: "campaign",
    title: "Outreach campaign started",
    projectName: "Restaurant Tenant Improvement",
    createdAt: "2026-08-23T10:00:00Z",
  },
];
