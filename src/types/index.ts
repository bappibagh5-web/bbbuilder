export type ProjectStatus =
  | "document-review"
  | "scope-review"
  | "trade-outreach"
  | "bid-collection"
  | "proposal-review"
  | "awarded";
export interface Project {
  id: string;
  projectNumber: string;
  name: string;
  client: string;
  address: string;
  city: string;
  province: string;
  postalCode: string;
  projectType: string;
  squareFootage: number;
  bidDeadline: string;
  questionsDeadline: string;
  status: ProjectStatus;
  progress: number;
  requiredTrades: number;
  documentsCount: number;
  invitedContractors: number;
  bidsReceived: number;
  createdAt: string;
  updatedAt: string;
}
export type DocumentCategory =
  | "Drawing Set"
  | "Specifications"
  | "Addendum"
  | "Bid Document"
  | "Bid Form"
  | "Schedule"
  | "Spreadsheet"
  | "Reference"
  | "Other";
export type DocumentProcessingStatus =
  | "Uploaded"
  | "Queued"
  | "Processing"
  | "Processed"
  | "Needs Review"
  | "Failed";
export type AIAnalysisStatus = DocumentProcessingStatus;
export interface DocumentExtractionSummary {
  discipline?: string;
  detectedSheets?: string[];
  summary?: string;
}
export interface ProjectDocument {
  id: string;
  projectId: string;
  name: string;
  category: DocumentCategory;
  fileType: string;
  fileSize: number;
  pages?: number;
  version: string;
  uploadedAt: string;
  uploadedBy: string;
  processingStatus: DocumentProcessingStatus;
  aiStatus: AIAnalysisStatus;
  isCurrentVersion: boolean;
  extraction?: DocumentExtractionSummary;
}
export interface TradeScope {
  id: string;
  projectId: string;
  trade: string;
  division: string;
  description: string;
  status: "draft" | "ai-review" | "approved";
  itemCount: number;
}
export type ContractorRelationship =
  "Preferred" | "Existing" | "New Prospect" | "Do Not Invite";
export type ContractorQualificationStatus =
  "Qualified" | "Conditionally Qualified" | "Needs Review" | "Unqualified";
export type ContractorRecordStatus = "Active" | "Inactive";
export type ContractorDiscoverySource =
  "Existing Database" | "Demo Discovery" | "Referral" | "Historical Project";
export type ContractorContactStatus =
  "Eligible" | "Suppressed" | "Do Not Contact" | "Needs Review";
export type ContractorCheckStatus =
  | "Verified"
  | "Confirmed"
  | "Strong"
  | "Needs Update"
  | "Unknown"
  | "Needs Review";
export interface ContractorQualification {
  insurance: ContractorCheckStatus;
  workersComp: ContractorCheckStatus;
  license: ContractorCheckStatus;
  commercialExperience: ContractorCheckStatus;
  retailExperience: ContractorCheckStatus;
}
export interface Subcontractor {
  id: string;
  companyName: string;
  primaryTrade: string;
  secondaryTrades: string[];
  city: string;
  province: string;
  serviceAreas: string[];
  phone: string;
  email: string;
  website: string;
  rating: number;
  reviewCount: number;
  relationship: ContractorRelationship;
  qualificationStatus: ContractorQualificationStatus;
  status: ContractorRecordStatus;
  yearsInBusiness: number;
  commercialExperience: string;
  retailExperience: string;
  qualification: ContractorQualification;
  lastBidDate?: string;
  totalInvitations: number;
  totalBids: number;
  awardedProjects: number;
  averageResponseTime: string;
  notes: string;
  source: ContractorDiscoverySource;
  contactStatus: ContractorContactStatus;
  contactSource: string;
  lastVerifiedAt: string;
  isDemo: true;
}
export interface ContractorFitScore {
  overall: number;
  tradeMatch: number;
  serviceAreaMatch: number;
  retailExperience: number;
  commercialExperience: number;
  qualification: number;
  relationship: number;
  responseHistory: number;
  reasons: string[];
  concerns: string[];
}
export type CandidateReviewStatus =
  "Not Reviewed" | "Approved" | "Needs Review" | "Excluded";
export type CandidateOutreachStatus = "Not Ready" | "Ready for Outreach";
export interface ProjectContractorCandidate {
  id: string;
  projectId: string;
  trade: string;
  subcontractorId: string;
  distanceKm: number;
  fit: ContractorFitScore;
  reviewStatus: CandidateReviewStatus;
  outreachStatus: CandidateOutreachStatus;
  shortlisted: boolean;
  exclusionReason?: string;
  discoverySourceLabel: string;
  searchQuery: string;
  searchArea: string;
  approvedBy?: string;
  approvedAt?: string;
}
export type ProcurementCoverage =
  "Insufficient" | "Needs More Candidates" | "Good" | "Strong";
export interface TradeProcurementStatus {
  trade: string;
  targetBids: number;
  approvedRecipients: number;
  expectedResponseRate: number;
  estimatedResponses: number;
  coverage: ProcurementCoverage;
  status: "Ready" | "Needs More Candidates";
}
export type CampaignStatus =
  | "Draft"
  | "Ready for Approval"
  | "Active"
  | "Needs Follow-Up"
  | "Needs Coverage"
  | "Complete"
  | "Closed";
export type RecipientResponseStatus =
  "No Response" | "Questions" | "Declined" | "Bid Submitted";
export type FollowUpStatus =
  | "Follow-Up Not Needed"
  | "Follow-Up Recommended"
  | "Follow-Up Sent"
  | "Do Not Follow Up"
  | "Declined"
  | "Bid Received";
export type CommunicationEventType =
  | "InvitationPrepared"
  | "InvitationSent"
  | "Delivered"
  | "Opened"
  | "ReplyReceived"
  | "QuestionReceived"
  | "Declined"
  | "BidSubmitted"
  | "FollowUpPrepared"
  | "FollowUpSent";
export interface CommunicationEvent {
  id: string;
  recipientId: string;
  type: CommunicationEventType;
  label: string;
  occurredAt: string;
  detail?: string;
}
export interface CampaignRecipient {
  id: string;
  campaignId: string;
  subcontractorId: string;
  sentAt?: string;
  delivered: boolean;
  openedAt?: string;
  response: RecipientResponseStatus;
  bidStatus: "None" | "Pending" | "Received";
  lastActivity: string;
  followUpStatus: FollowUpStatus;
  declineReason?: string;
  question?: string;
  questionStatus?: "Requires Response" | "Reviewed";
  events: CommunicationEvent[];
}
export interface OutreachCampaign {
  id: string;
  projectId: string;
  projectName: string;
  trade: string;
  recipientIds: string[];
  sent: number;
  opened: number;
  responses: number;
  bids: number;
  deadline: string;
  status: CampaignStatus;
  scopeApproved: boolean;
  packageApproved: boolean;
  targetBids: number;
}
export interface CampaignApprovalState {
  tradeScope: boolean;
  bidPackage: boolean;
  recipients: boolean;
  bidDeadline: boolean;
  emailContent: boolean;
  documents: boolean;
}
export interface BidAttachment {
  id: string;
  filename: string;
  kind: "Proposal" | "Supporting Document";
  isDemo: true;
}
export type BidCompleteness = "Complete" | "Incomplete";
export type BidReviewStatus = "Reviewed" | "Needs Review";
export type BidSubmissionStatus =
  "Ready for Comparison" | "Needs Review" | "Needs Clarification";
export interface BidExtraction {
  baseBid: number;
  taxes: string;
  labour: string;
  materials: string;
  permit: string;
  fixtures: string;
  schedule: string;
  validity: string;
  exclusions: string[];
  allowances: string[];
  alternates: string[];
  missingItems: string[];
  scopeCoverage: number;
  confidence: number;
}
export type ClarificationStatus = "Open" | "Prepared" | "Resolved" | "Waived";
export interface BidClarification {
  id: string;
  bidSubmissionId: string;
  category: string;
  question: string;
  status: ClarificationStatus;
  priority: "Low" | "Medium" | "High";
  sourceField: string;
}
export interface BidSubmission {
  id: string;
  projectId: string;
  campaignId: string;
  campaignRecipientId: string;
  subcontractorId: string;
  trade: string;
  submittedAt: string;
  submittedBy: string;
  total: number;
  completeness: BidCompleteness;
  reviewStatus: BidReviewStatus;
  status: BidSubmissionStatus;
  attachment: BidAttachment;
  extraction: BidExtraction;
  clarifications: BidClarification[];
}
export interface BidReviewChecklist {
  total: boolean;
  scopeCoverage: boolean;
  exclusions: boolean;
  schedule: boolean;
  clarifications: boolean;
}
export type ComparisonStatus =
  | "Not Ready"
  | "Needs More Bids"
  | "Ready for Review"
  | "Clarifications Required"
  | "Selection Approved"
  | "Closed";
export type NormalizationCategory =
  | "Missing Scope"
  | "Excluded Scope"
  | "Allowance"
  | "Clarification"
  | "Estimator Adjustment"
  | "Other";
export interface NormalizationAdjustment {
  id: string;
  bidSubmissionId: string;
  category: NormalizationCategory;
  description: string;
  amount: number;
  reason: string;
  source: "Demo Assumption" | "Estimator";
  humanEditable: boolean;
}
export interface BidNormalization {
  bidSubmissionId: string;
  baseBid: number;
  adjustments: NormalizationAdjustment[];
}
export interface LeveledBid {
  id: string;
  bidSubmissionId: string;
  subcontractorId: string;
  normalization: BidNormalization;
  emergencyLighting: string;
  fireAlarm: string;
  security: string;
  riskLevel: "Low" | "Low–Moderate" | "High";
  riskReasons: string[];
  reviewPosition:
    | "Strong Candidate"
    | "Competitive Candidate"
    | "Needs Clarification"
    | "High Risk";
}
export interface ComparisonQueueItem {
  id: string;
  projectId: string;
  projectName: string;
  trade: string;
  bids: number;
  priceRange: string;
  coverageRange: string;
  clarifications: number;
  recommendation: string;
  status: ComparisonStatus;
}
export interface EstimatorSelection {
  trade: string;
  subcontractorId: string;
  selectedBy: string;
  selectedAt: string;
  basis: "Recommended Candidate" | "Estimator Override";
  overrideReason?: string;
  notes?: string;
}
export type ProposalStatus =
  | "Draft"
  | "Internal Review"
  | "Approved"
  | "Issued"
  | "Revision Requested"
  | "Accepted"
  | "Declined"
  | "Superseded";
export type ClientDecision =
  "Pending" | "Revision Requested" | "Accepted" | "Declined";
export type PricingSourceType =
  | "Selected Bid"
  | "Normalized Selected Bid"
  | "Estimator Allowance"
  | "Projected Trade Cost";
export interface ProposalTradeLine {
  id: string;
  trade: string;
  selection: string;
  sourceType: PricingSourceType;
  internalCost: number;
  clientPrice: number;
}
export interface ProposalAllowance {
  id: string;
  name: string;
  amount: number;
  description: string;
  includedInTotal: boolean;
  clientVisible: boolean;
}
export interface ProposalAlternate {
  id: string;
  name: string;
  amount: number;
  status:
    | "Included in Base Proposal"
    | "Optional Add"
    | "Optional Deduct"
    | "Not Included";
}
export interface ProposalVersion {
  version: number;
  createdAt: string;
  status: ProposalStatus;
}
export interface ProposalPricingSettings {
  generalConditions: number;
  permitAllowance: number;
  projectManagement: number;
  contingencyPercent: number;
  overheadProfitPercent: number;
  taxPercent: number;
}
export interface Proposal {
  id: string;
  projectId: string;
  projectName: string;
  client: string;
  version: number;
  preparedBy: string;
  updatedAt: string;
  status: ProposalStatus;
  clientDecision: ClientDecision;
  tradeLines: ProposalTradeLine[];
  allowances: ProposalAllowance[];
  alternates: ProposalAlternate[];
  exclusions: string[];
  clarifications: string[];
  versions: ProposalVersion[];
  settings: ProposalPricingSettings;
  projectSummary: string;
  includedScope: string[];
  schedule: string[];
  paymentTerms: string[];
  warranty: string[];
}
export interface AwardedProject {
  id: string;
  projectId: string;
  projectName: string;
  client: string;
  contractValue: number;
  awardedAt: string;
  tradeAwards: string;
  compliance: string;
  schedule: string;
  status: string;
}
export interface BidInvitation {
  id: string;
  projectId: string;
  tradeId: string;
  subcontractorId: string;
  sentAt: string;
  viewedAt?: string;
  respondedAt?: string;
  status: "queued" | "sent" | "viewed" | "responded" | "declined";
}
export interface Bid {
  id: string;
  projectId: string;
  tradeId: string;
  subcontractorId: string;
  total: number;
  laborIncluded: boolean;
  materialsIncluded: boolean;
  permitsIncluded: boolean;
  schedule: string;
  inclusions: string[];
  exclusions: string[];
  missingItems: string[];
  scopeCoverage: number;
  aiConfidence: number;
  recommendationStatus: "unreviewed" | "recommended" | "alternate" | "excluded";
}
export interface ActivityEvent {
  id: string;
  type: "bid" | "ai" | "scope" | "campaign" | "project";
  title: string;
  projectName: string;
  createdAt: string;
}
export interface AttentionItem {
  id: string;
  projectName: string;
  message: string;
  severity: "warning" | "critical" | "ai" | "info";
}
export type WorkflowStageStatus =
  "complete" | "current" | "upcoming" | "attention";
export interface ProjectWorkflowStage {
  id: string;
  label: string;
  status: WorkflowStageStatus;
}
export type TradeCoverageStatus =
  "ready" | "collecting" | "needs-coverage" | "not-started";
export interface TradeBidStatus {
  id: string;
  trade: string;
  bidsReceived: number;
  status: TradeCoverageStatus;
}
export interface ProjectAttentionItem {
  id: string;
  title: string;
  message: string;
  severity: "warning" | "critical" | "info";
}
export interface ProjectDetails {
  projectId: string;
  workflow: ProjectWorkflowStage[];
  trades: TradeBidStatus[];
  attention: ProjectAttentionItem[];
  activity: ActivityEvent[];
}
export interface DocumentSourceReference {
  documentId: string;
  documentName: string;
  sheetNumber?: string;
  pageNumber?: number;
  sourceLabel: string;
}
export interface AIExtractedField {
  id: string;
  label: string;
  value: string;
  confidence: number;
  source?: DocumentSourceReference;
  editable: boolean;
}
export interface AITradeFinding {
  id: string;
  trade: string;
  confidence: number;
  sourceCount: number;
  status: "recommended" | "optional";
}
export interface AIScopeObservation {
  id: string;
  category:
    | "General"
    | "Architectural"
    | "Mechanical"
    | "Plumbing"
    | "Electrical"
    | "Fire Protection"
    | "Specifications";
  finding: string;
  confidence: number;
  source: DocumentSourceReference;
}
export interface AIRiskFinding {
  id: string;
  title: string;
  reason: string;
  severity: "Low" | "Medium" | "High";
  source?: DocumentSourceReference;
}
export interface AIPotentialExclusion {
  id: string;
  label: string;
  status: "Potential Exclusion" | "Needs Confirmation";
}
export interface AIReviewData {
  projectId: string;
  status:
    | "Analysis In Progress"
    | "Awaiting Documents"
    | "Ready for Human Review"
    | "Review Approved";
  documentsAnalyzed: number;
  drawingSheetsReviewed: number;
  findingsCount: number;
  attentionCount: number;
  overallConfidence: number;
  fields: AIExtractedField[];
  disciplines: string[];
  trades: AITradeFinding[];
  observations: AIScopeObservation[];
  risks: AIRiskFinding[];
  exclusions: AIPotentialExclusion[];
}
export interface AIReviewApprovalState {
  projectInformation: boolean;
  requiredTrades: boolean;
  scopeObservations: boolean;
  riskItems: boolean;
  potentialExclusions: boolean;
}
export type ScopeItemCategory =
  | "Included Scope"
  | "Exclusion"
  | "Clarification"
  | "Allowance"
  | "Alternate"
  | "General Requirement";
export type ScopeItemReviewStatus =
  "AI Generated" | "Reviewed" | "Human Revised" | "Human Added" | "Removed";
export type TradeScopeStatus =
  | "Draft"
  | "Needs Review"
  | "Ready for Approval"
  | "Approved"
  | "Human Revised";
export type BidPackageStatus =
  "Not Generated" | "Draft" | "Ready for Review" | "Approved for Outreach";
export interface TradeScopeItem {
  id: string;
  tradeId: string;
  category: ScopeItemCategory;
  description: string;
  status: ScopeItemReviewStatus;
  confidence?: number;
  sources: DocumentSourceReference[];
  humanModified: boolean;
  originalDescription?: string;
  notes?: string;
}
export interface TradeScopeWarning {
  id: string;
  tradeId: string;
  message: string;
  reviewed?: boolean;
}
export interface TradeScopeDetail {
  id: string;
  projectId: string;
  trade: string;
  status: TradeScopeStatus;
  confidence: number;
  sourceCount: number;
  packageStatus: BidPackageStatus;
  items: TradeScopeItem[];
  warnings: TradeScopeWarning[];
  approvedBy?: string;
  approvedAt?: string;
}
export interface TradeScopeReview {
  scopeItems: boolean;
  exclusions: boolean;
  clarifications: boolean;
  sources: boolean;
}
export interface BidPackageDocument {
  documentId: string;
  documentName: string;
  included: boolean;
}
export interface BidPackageReviewState {
  tradeScope: boolean;
  exclusions: boolean;
  bidDeadline: boolean;
  documentList: boolean;
  submissionInstructions: boolean;
}
export interface BidPackage {
  id: string;
  projectId: string;
  tradeId: string;
  status: BidPackageStatus;
  requirements: string[];
  submissionInstructions: string[];
  documents: BidPackageDocument[];
}
