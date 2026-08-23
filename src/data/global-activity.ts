export type GlobalActivityType =
  | "Project"
  | "Documents"
  | "AI Review"
  | "Trade Scope"
  | "Bid Package"
  | "Outreach"
  | "Bid Submission"
  | "Clarification"
  | "Trade Selection"
  | "Client Proposal"
  | "Award";

export interface GlobalActivityItem {
  id: string;
  projectId: string;
  projectName: string;
  type: GlobalActivityType;
  title: string;
  actor: string;
  occurredAt: string;
}

export const globalActivity: GlobalActivityItem[] = [
  {
    id: "ga-12",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "Client Proposal",
    title: "Client proposal approved for issue",
    actor: "Alex Morgan",
    occurredAt: "2026-08-23T11:55:00Z",
  },
  {
    id: "ga-11",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "Trade Selection",
    title: "Demo Pacific Electrical Ltd. selected for Electrical",
    actor: "Alex Morgan",
    occurredAt: "2026-08-23T11:45:00Z",
  },
  {
    id: "ga-10",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "Clarification",
    title: "Electrical bid clarification resolved",
    actor: "Alex Morgan",
    occurredAt: "2026-08-23T11:30:00Z",
  },
  {
    id: "ga-9",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "Bid Submission",
    title: "Electrical bid received from Demo Pacific Electrical Ltd.",
    actor: "System",
    occurredAt: "2026-08-23T11:15:00Z",
  },
  {
    id: "ga-8",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "Outreach",
    title: "Demo bid invitations sent",
    actor: "Alex Morgan",
    occurredAt: "2026-08-22T17:00:00Z",
  },
  {
    id: "ga-7",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "Bid Package",
    title: "Electrical bid package approved for outreach",
    actor: "Alex Morgan",
    occurredAt: "2026-08-22T16:10:00Z",
  },
  {
    id: "ga-6",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "Trade Scope",
    title: "Electrical trade scope approved",
    actor: "Alex Morgan",
    occurredAt: "2026-08-22T15:45:00Z",
  },
  {
    id: "ga-5",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "AI Review",
    title: "AI-assisted review approved by estimator",
    actor: "Alex Morgan",
    occurredAt: "2026-08-22T14:20:00Z",
  },
  {
    id: "ga-4",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "Documents",
    title: "34 project documents processed",
    actor: "System",
    occurredAt: "2026-08-22T13:00:00Z",
  },
  {
    id: "ga-3",
    projectId: "fashion-retail-burnaby",
    projectName: "Fashion Retail Fit-Out",
    type: "Trade Scope",
    title: "HVAC trade scope approved",
    actor: "Jordan Lee",
    occurredAt: "2026-08-22T11:00:00Z",
  },
  {
    id: "ga-2",
    projectId: "office-renovation-richmond",
    projectName: "Commercial Office Renovation",
    type: "Award",
    title: "Project converted to Awarded Project",
    actor: "Priya Shah",
    occurredAt: "2026-08-17T16:00:00Z",
  },
  {
    id: "ga-1",
    projectId: "retail-store-coquitlam",
    projectName: "Retail Store Tenant Improvement",
    type: "Project",
    title: "Project created",
    actor: "Alex Morgan",
    occurredAt: "2026-08-01T10:00:00Z",
  },
];
