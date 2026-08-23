import type {
  ProjectContractorCandidate,
  TradeProcurementStatus,
} from "@/types";
import { subcontractors } from "./subcontractors";

const electrical = subcontractors.filter(
  (item) => item.primaryTrade === "Electrical",
);
export const electricalCandidates: ProjectContractorCandidate[] =
  electrical.map((company, index) => {
    const overall =
      [92, 88, 84, 81, 78, 76, 90, 73, 69, 82, 71, 42][index] ?? 70;
    return {
      id: `candidate-${company.id}`,
      projectId: "retail-store-coquitlam",
      trade: "Electrical",
      subcontractorId: company.id,
      distanceKm: [12, 8, 28, 34, 36, 21, 5, 31, 29, 39, 7, 33][index] ?? 20,
      fit: {
        overall,
        tradeMatch: 20,
        serviceAreaMatch: index === 9 ? 12 : 15,
        retailExperience: index % 3 === 0 ? 15 : 10,
        commercialExperience: 15,
        qualification:
          company.qualificationStatus === "Qualified"
            ? 15
            : company.qualificationStatus === "Unqualified"
              ? 2
              : 8,
        relationship:
          company.relationship === "Preferred"
            ? 10
            : company.relationship === "Existing"
              ? 7
              : 3,
        responseHistory: overall > 80 ? 10 : 5,
        reasons: [
          "Exact electrical trade match",
          "Serves Coquitlam and the Lower Mainland",
          company.retailExperience,
          `${company.qualificationStatus} demo vendor`,
          `${company.relationship} relationship`,
        ],
        concerns:
          company.contactStatus !== "Eligible"
            ? [`Contact status: ${company.contactStatus}`]
            : index % 4 === 0
              ? ["Current workload unknown"]
              : [],
      },
      reviewStatus:
        index < 6
          ? "Approved"
          : index === 8
            ? "Needs Review"
            : index === 11
              ? "Excluded"
              : "Not Reviewed",
      outreachStatus: index < 6 ? "Ready for Outreach" : "Not Ready",
      shortlisted: index < 8,
      exclusionReason: index === 11 ? "Qualification incomplete" : undefined,
      discoverySourceLabel:
        company.source === "Demo Discovery"
          ? "Demo Search Dataset"
          : "Existing BB Builders Demo Database",
      searchQuery: "commercial electrician Coquitlam",
      searchArea: "40 km",
      approvedBy: index < 6 ? "Alex Morgan · Estimator" : undefined,
      approvedAt: index < 6 ? "August 23, 2026 at 2:15 PM" : undefined,
    };
  });

export const procurementStatuses: TradeProcurementStatus[] = [
  ["Demolition", 5, 5, 65, 3, "Good", "Ready"],
  ["Framing / Drywall", 5, 6, 65, 4, "Strong", "Ready"],
  ["Painting", 4, 5, 70, 4, "Strong", "Ready"],
  ["Flooring", 4, 3, 60, 2, "Needs More Candidates", "Needs More Candidates"],
  ["Millwork", 4, 4, 65, 3, "Good", "Ready"],
  ["Plumbing", 4, 5, 65, 3, "Good", "Ready"],
  ["HVAC", 4, 5, 65, 3, "Good", "Ready"],
  ["Electrical", 5, 6, 65, 4, "Good", "Ready"],
  [
    "Fire Protection",
    4,
    3,
    60,
    2,
    "Needs More Candidates",
    "Needs More Candidates",
  ],
  ["Cleaning", 4, 4, 70, 3, "Good", "Ready"],
].map(
  ([
    trade,
    targetBids,
    approvedRecipients,
    expectedResponseRate,
    estimatedResponses,
    coverage,
    status,
  ]) => ({
    trade: trade as string,
    targetBids: targetBids as number,
    approvedRecipients: approvedRecipients as number,
    expectedResponseRate: expectedResponseRate as number,
    estimatedResponses: estimatedResponses as number,
    coverage: coverage as TradeProcurementStatus["coverage"],
    status: status as TradeProcurementStatus["status"],
  }),
);

export const contractorDiscoverySummary = {
  candidatesIdentified: 86,
  shortlisted: 46,
  approvedForOutreach: 38,
  tradesRequired: procurementStatuses.length,
  tradesReady: procurementStatuses.filter((item) => item.status === "Ready")
    .length,
  tradesNeedingMoreCandidates: procurementStatuses.filter(
    (item) => item.status === "Needs More Candidates",
  ).length,
};

export const discoveryTrades = procurementStatuses.map((item) => item.trade);
export function getContractorCandidates(projectId: string, trade: string) {
  return projectId === "retail-store-coquitlam" && trade === "Electrical"
    ? electricalCandidates
    : [];
}
