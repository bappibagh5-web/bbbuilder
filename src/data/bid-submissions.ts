import type { BidSubmission } from "@/types";
const base = (
  id: string,
  subcontractorId: string,
  total: number,
  complete: boolean,
): BidSubmission => ({
  id,
  projectId: "retail-store-coquitlam",
  campaignId: "campaign-electrical",
  campaignRecipientId: `recipient-${subcontractorId}`,
  subcontractorId,
  trade: "Electrical",
  submittedAt: id.includes("pacific") ? "Aug 21, 3:42 PM" : "Aug 22, 2:18 PM",
  submittedBy: `estimating@${subcontractorId}.example.com`,
  total,
  completeness: complete ? "Complete" : "Incomplete",
  reviewStatus: complete ? "Reviewed" : "Needs Review",
  status: complete ? "Ready for Comparison" : "Needs Clarification",
  attachment: {
    id: `attachment-${id}`,
    filename: `${id.includes("pacific") ? "Demo_Pacific" : id.includes("tricity") ? "Demo_TriCity" : "Demo_Fraser"}_Electrical_Proposal.pdf`,
    kind: "Proposal",
    isDemo: true,
  },
  extraction: {
    baseBid: total,
    taxes: "Excluded / Additional",
    labour: "Included",
    materials: "Included",
    permit: complete ? "Included" : "Not Specified",
    fixtures: complete ? "Included" : "Excluded",
    schedule: complete ? "4 weeks" : "Not Provided",
    validity: complete ? "30 days" : "Not Specified",
    exclusions: complete
      ? ["Fire alarm", "Security system"]
      : ["Lighting fixtures"],
    allowances: ["None identified"],
    alternates: ["None identified"],
    missingItems: complete
      ? []
      : [
          "Permit responsibility",
          "Schedule duration",
          "Bid validity",
          "Emergency lighting confirmation",
        ],
    scopeCoverage: complete ? 91 : 73,
    confidence: complete ? 94 : 78,
  },
  clarifications: [],
});
const pacific = base("bid-pacific", "demo-pacific-electrical-ltd", 42850, true);
pacific.clarifications = [
  {
    id: "clarification-pacific-1",
    bidSubmissionId: pacific.id,
    category: "Scope",
    question: "Please confirm fire alarm work remains excluded from this bid.",
    status: "Resolved",
    priority: "Low",
    sourceField: "Exclusions",
  },
];
const tricity = base(
  "bid-tricity",
  "demo-tricity-commercial-electric",
  39200,
  false,
);
tricity.clarifications = [
  {
    id: "clarification-tricity-1",
    bidSubmissionId: tricity.id,
    category: "Permit Responsibility",
    question:
      "Please confirm whether electrical permit fees and permit coordination are included in your submitted price.",
    status: "Open",
    priority: "High",
    sourceField: "Permit",
  },
  {
    id: "clarification-tricity-2",
    bidSubmissionId: tricity.id,
    category: "Schedule",
    question: "Please provide the anticipated construction duration.",
    status: "Open",
    priority: "Medium",
    sourceField: "Schedule",
  },
  {
    id: "clarification-tricity-3",
    bidSubmissionId: tricity.id,
    category: "Bid Validity",
    question: "Please confirm the proposal validity period.",
    status: "Open",
    priority: "Medium",
    sourceField: "Validity",
  },
];
const fraser = base("bid-fraser", "demo-fraser-valley-electrical", 45600, true);
fraser.extraction.scopeCoverage = 96;
fraser.extraction.confidence = 95;
export const bidSubmissions = [pacific, tricity, fraser];
export const bidInboxSummary = {
  received: 31,
  trades: 10,
  needsReview: 6,
  clarifications: 4,
  ready: 21,
};
