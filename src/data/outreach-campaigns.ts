import type { CampaignRecipient, OutreachCampaign } from "@/types";
import { electricalCandidates } from "./contractor-discovery";
const rows: Array<
  [
    string,
    string,
    string,
    string,
    number,
    number,
    number,
    number,
    number,
    string,
    OutreachCampaign["status"],
    number,
  ]
> = [
  [
    "electrical",
    "retail-store-coquitlam",
    "Retail Store Tenant Improvement",
    "Electrical",
    6,
    6,
    5,
    5,
    4,
    "2026-09-14",
    "Active",
    5,
  ],
  [
    "plumbing",
    "retail-store-coquitlam",
    "Retail Store Tenant Improvement",
    "Plumbing",
    5,
    5,
    5,
    4,
    3,
    "2026-09-14",
    "Active",
    4,
  ],
  [
    "hvac",
    "retail-store-coquitlam",
    "Retail Store Tenant Improvement",
    "HVAC",
    5,
    5,
    4,
    4,
    3,
    "2026-09-14",
    "Active",
    4,
  ],
  [
    "fire",
    "retail-store-coquitlam",
    "Retail Store Tenant Improvement",
    "Fire Protection",
    3,
    3,
    2,
    2,
    2,
    "2026-09-14",
    "Needs Coverage",
    4,
  ],
  [
    "flooring",
    "retail-store-coquitlam",
    "Retail Store Tenant Improvement",
    "Flooring",
    3,
    3,
    3,
    2,
    2,
    "2026-09-14",
    "Needs Coverage",
    4,
  ],
  [
    "painting-burnaby",
    "fashion-retail-burnaby",
    "Fashion Retail Renovation",
    "Painting",
    5,
    5,
    4,
    3,
    2,
    "2026-09-19",
    "Needs Follow-Up",
    4,
  ],
  [
    "plumbing-vancouver",
    "restaurant-vancouver",
    "Restaurant Tenant Improvement",
    "Plumbing",
    6,
    6,
    5,
    4,
    3,
    "2026-09-22",
    "Active",
    4,
  ],
  [
    "demolition-office",
    "office-renovation-richmond",
    "Office Renovation",
    "Demolition",
    4,
    4,
    4,
    4,
    3,
    "2026-09-28",
    "Complete",
    3,
  ],
];
export const outreachCampaigns: OutreachCampaign[] = rows.map(
  (
    [
      id,
      projectId,
      projectName,
      trade,
      recipients,
      sent,
      opened,
      responses,
      bids,
      deadline,
      status,
      targetBids,
    ],
    index,
  ) => ({
    id: `campaign-${id}`,
    projectId,
    projectName,
    trade,
    recipientIds:
      index === 0
        ? electricalCandidates
            .slice(0, recipients)
            .map((item) => `recipient-${item.subcontractorId}`)
        : Array.from(
            { length: recipients },
            (_, i) => `campaign-${id}-recipient-${i + 1}`,
          ),
    sent,
    opened,
    responses,
    bids,
    deadline,
    status,
    scopeApproved: true,
    packageApproved: true,
    targetBids,
  }),
);
const responseData: Array<
  [
    CampaignRecipient["response"],
    CampaignRecipient["bidStatus"],
    string,
    CampaignRecipient["followUpStatus"],
  ]
> = [
  ["Bid Submitted", "Received", "Aug 22, 2:31 PM", "Bid Received"],
  ["Bid Submitted", "Received", "Aug 22, 4:10 PM", "Bid Received"],
  ["Questions", "Pending", "Aug 21, 11:14 AM", "Follow-Up Not Needed"],
  ["Declined", "None", "Aug 21, 1:25 PM", "Declined"],
  ["No Response", "None", "Aug 20, 9:05 AM", "Follow-Up Recommended"],
  ["Bid Submitted", "Received", "Aug 22, 3:48 PM", "Bid Received"],
];
export const electricalRecipients: CampaignRecipient[] = electricalCandidates
  .slice(0, 6)
  .map((candidate, index) => {
    const id = `recipient-${candidate.subcontractorId}`;
    const [response, bidStatus, lastActivity, followUpStatus] =
      responseData[index];
    const events: CampaignRecipient["events"] = [
      {
        id: `${id}-prepared`,
        recipientId: id,
        type: "InvitationPrepared",
        label: "Bid invitation prepared",
        occurredAt: "Aug 20, 8:52 AM",
      },
      {
        id: `${id}-sent`,
        recipientId: id,
        type: "InvitationSent",
        label: "Bid invitation sent",
        occurredAt: "Aug 20, 9:05 AM",
      },
      {
        id: `${id}-delivered`,
        recipientId: id,
        type: "Delivered",
        label: "Delivered",
        occurredAt: "Aug 20, 9:06 AM",
      },
    ];
    if (index !== 4)
      events.push({
        id: `${id}-opened`,
        recipientId: id,
        type: "Opened",
        label: "Invitation opened",
        occurredAt: index === 0 ? "Aug 20, 9:18 AM" : "Aug 20, 10:02 AM",
      });
    if (response === "Bid Submitted")
      events.push({
        id: `${id}-bid`,
        recipientId: id,
        type: "BidSubmitted",
        label: "Bid submitted",
        occurredAt: lastActivity,
        detail: `Demo_${index === 0 ? "Pacific" : index === 1 ? "TriCity" : "Fraser"}_Electrical_Proposal.pdf received`,
      });
    if (response === "Questions")
      events.push({
        id: `${id}-question`,
        recipientId: id,
        type: "QuestionReceived",
        label: "Question received",
        occurredAt: lastActivity,
        detail:
          "Please confirm whether fire alarm work is included in the electrical scope.",
      });
    if (response === "Declined")
      events.push({
        id: `${id}-declined`,
        recipientId: id,
        type: "Declined",
        label: "Invitation declined",
        occurredAt: lastActivity,
        detail: "Unable to meet bid deadline",
      });
    return {
      id,
      campaignId: "campaign-electrical",
      subcontractorId: candidate.subcontractorId,
      sentAt: "Aug 20, 9:05 AM",
      delivered: true,
      openedAt:
        index === 4
          ? undefined
          : index === 0
            ? "Aug 20, 9:18 AM"
            : "Aug 20, 10:02 AM",
      response,
      bidStatus,
      lastActivity,
      followUpStatus,
      declineReason:
        response === "Declined" ? "Unable to meet bid deadline" : undefined,
      question:
        response === "Questions"
          ? "Please confirm whether fire alarm work is included in the electrical scope."
          : undefined,
      questionStatus:
        response === "Questions" ? "Requires Response" : undefined,
      events,
    };
  });
export const campaignSummary = {
  active: 8,
  sent: 86,
  responses: 51,
  bids: 31,
  followUp: 18,
};
export const outreachTradeSummary = [
  ["Demolition", 5, 4, "Ready"],
  ["Framing / Drywall", 6, 3, "Collection Active"],
  ["Painting", 5, 4, "Ready"],
  ["Flooring", 3, 2, "Needs More Bids"],
  ["Millwork", 4, 3, "Ready"],
  ["Plumbing", 5, 3, "Ready"],
  ["HVAC", 5, 3, "Collection Active"],
  ["Electrical", 6, 4, "Ready"],
  ["Fire Protection", 3, 2, "Needs More Bids"],
  ["Cleaning", 4, 3, "Ready"],
].map(([trade, invited, bids, status]) => ({
  trade: trade as string,
  invited: invited as number,
  bids: bids as number,
  status: status as string,
}));
