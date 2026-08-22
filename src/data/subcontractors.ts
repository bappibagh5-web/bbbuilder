import type {
  ContractorQualificationStatus,
  ContractorRelationship,
  Subcontractor,
} from "@/types";

const tradeCompanies: Array<[string, string, string, string]> = [
  ["Demo Pacific Electrical Ltd.", "Electrical", "Burnaby", "Preferred"],
  [
    "Demo TriCity Commercial Electric",
    "Electrical",
    "Port Coquitlam",
    "Existing",
  ],
  ["Demo Metro Electrical Contractors", "Electrical", "Vancouver", "Existing"],
  ["Demo Fraser Valley Electrical", "Electrical", "Surrey", "New Prospect"],
  ["Demo West Coast Power Systems", "Electrical", "Richmond", "New Prospect"],
  [
    "Demo Apex Retail Electrical",
    "Electrical",
    "New Westminster",
    "New Prospect",
  ],
  ["Demo Evergreen Electric Group", "Electrical", "Coquitlam", "Preferred"],
  ["Demo Skyline Electrical Services", "Electrical", "Delta", "Existing"],
  [
    "Demo Harbour Commercial Electric",
    "Electrical",
    "North Vancouver",
    "New Prospect",
  ],
  ["Demo Keystone Power & Controls", "Electrical", "Langley", "Existing"],
  [
    "Demo Brightline Electrical Works",
    "Electrical",
    "Port Moody",
    "New Prospect",
  ],
  ["Demo Central City Electric", "Electrical", "Surrey", "Do Not Invite"],
  ["Demo Westline Mechanical Inc.", "HVAC", "Coquitlam", "Preferred"],
  ["Demo Fraser Plumbing Group", "Plumbing", "Surrey", "Existing"],
  ["Demo Metro Fire Protection Ltd.", "Fire Protection", "Burnaby", "Existing"],
  ["Demo Northshore Millwork Inc.", "Millwork", "North Vancouver", "Preferred"],
  ["Demo Coastal Flooring Group", "Flooring", "Richmond", "New Prospect"],
  ["Demo Summit Interiors Ltd.", "Framing / Drywall", "Vancouver", "Existing"],
  ["Demo Precision Painting Co.", "Painting", "New Westminster", "Existing"],
  [
    "Demo ClearSite Construction Cleaning",
    "Cleaning",
    "Surrey",
    "New Prospect",
  ],
  ["Demo Lower Mainland Demolition Ltd.", "Demolition", "Delta", "Preferred"],
];

const qualificationByIndex: ContractorQualificationStatus[] = [
  "Qualified",
  "Qualified",
  "Conditionally Qualified",
  "Needs Review",
  "Qualified",
  "Needs Review",
  "Qualified",
  "Conditionally Qualified",
  "Needs Review",
  "Qualified",
  "Needs Review",
  "Unqualified",
];

export const subcontractors: Subcontractor[] = tradeCompanies.map(
  ([companyName, primaryTrade, city, relationship], index) => {
    const slug = companyName
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    const qualificationStatus =
      qualificationByIndex[index % qualificationByIndex.length];
    const incomplete =
      qualificationStatus === "Needs Review" ||
      qualificationStatus === "Unqualified";
    return {
      id: slug,
      companyName,
      primaryTrade,
      secondaryTrades: primaryTrade === "Electrical" ? ["Controls"] : [],
      city,
      province: "BC",
      serviceAreas: [city, "Coquitlam", "Lower Mainland"],
      phone: `604-555-${String(1200 + index).padStart(4, "0")}`,
      email: `estimating@${slug}.example.com`,
      website: `https://${slug}.example.com`,
      rating: Number((4.9 - (index % 7) * 0.2).toFixed(1)),
      reviewCount: 8 + ((index * 7) % 53),
      relationship: relationship as ContractorRelationship,
      qualificationStatus,
      status: index === 11 ? "Inactive" : "Active",
      yearsInBusiness: 6 + (index % 18),
      commercialExperience:
        index % 4 === 0
          ? "Extensive commercial portfolio"
          : "Confirmed commercial experience",
      retailExperience:
        index % 3 === 0
          ? "Strong retail tenant-improvement experience"
          : "Moderate retail experience",
      qualification: {
        insurance: incomplete ? "Needs Update" : "Verified",
        workersComp: incomplete ? "Unknown" : "Verified",
        license: incomplete ? "Needs Review" : "Verified",
        commercialExperience: "Confirmed",
        retailExperience: index % 3 === 0 ? "Strong" : "Confirmed",
      },
      lastBidDate: `2026-0${(index % 8) + 1}-12`,
      totalInvitations: 6 + (index % 12),
      totalBids: 3 + (index % 9),
      awardedProjects: index % 5,
      averageResponseTime: `${(1.2 + (index % 6) * 0.3).toFixed(1)} days`,
      notes: "Fictional demo record for procurement workflow review.",
      source:
        index % 4 === 0
          ? "Historical Project"
          : index % 5 === 0
            ? "Referral"
            : index < 14
              ? "Existing Database"
              : "Demo Discovery",
      contactStatus:
        index === 11
          ? "Do Not Contact"
          : index === 8
            ? "Suppressed"
            : incomplete
              ? "Needs Review"
              : "Eligible",
      contactSource: "Demo estimating contact",
      lastVerifiedAt: "2026-08-20",
      isDemo: true,
    };
  },
);

export const subcontractorSummary = {
  total: 126,
  active: 84,
  prospects: 28,
  needsQualification: 14,
  tradesCovered: 15,
};
export function getSubcontractor(id: string) {
  return subcontractors.find((item) => item.id === id);
}
