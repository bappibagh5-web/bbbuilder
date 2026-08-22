export type ProjectStatus="document-review"|"scope-review"|"trade-outreach"|"bid-collection"|"proposal-review"|"awarded";
export interface Project{id:string;projectNumber:string;name:string;client:string;address:string;city:string;province:string;postalCode:string;projectType:string;squareFootage:number;bidDeadline:string;questionsDeadline:string;status:ProjectStatus;progress:number;requiredTrades:number;documentsCount:number;invitedContractors:number;bidsReceived:number;createdAt:string;updatedAt:string}
export type DocumentCategory="Drawing Set"|"Specifications"|"Addendum"|"Bid Document"|"Bid Form"|"Schedule"|"Spreadsheet"|"Reference"|"Other";
export type DocumentProcessingStatus="Uploaded"|"Queued"|"Processing"|"Processed"|"Needs Review"|"Failed";
export type AIAnalysisStatus=DocumentProcessingStatus;
export interface DocumentExtractionSummary{discipline?:string;detectedSheets?:string[];summary?:string}
export interface ProjectDocument{id:string;projectId:string;name:string;category:DocumentCategory;fileType:string;fileSize:number;pages?:number;version:string;uploadedAt:string;uploadedBy:string;processingStatus:DocumentProcessingStatus;aiStatus:AIAnalysisStatus;isCurrentVersion:boolean;extraction?:DocumentExtractionSummary}
export interface TradeScope{id:string;projectId:string;trade:string;division:string;description:string;status:"draft"|"ai-review"|"approved";itemCount:number}
export interface Subcontractor{id:string;name:string;trades:string[];city:string;province:string;contactName:string;email:string;phone:string;status:"active"|"inactive"|"pending";isDemo:true}
export interface BidInvitation{id:string;projectId:string;tradeId:string;subcontractorId:string;sentAt:string;viewedAt?:string;respondedAt?:string;status:"queued"|"sent"|"viewed"|"responded"|"declined"}
export interface Bid{id:string;projectId:string;tradeId:string;subcontractorId:string;total:number;laborIncluded:boolean;materialsIncluded:boolean;permitsIncluded:boolean;schedule:string;inclusions:string[];exclusions:string[];missingItems:string[];scopeCoverage:number;aiConfidence:number;recommendationStatus:"unreviewed"|"recommended"|"alternate"|"excluded"}
export interface ActivityEvent{id:string;type:"bid"|"ai"|"scope"|"campaign"|"project";title:string;projectName:string;createdAt:string}
export interface AttentionItem{id:string;projectName:string;message:string;severity:"warning"|"critical"|"ai"|"info"}
export type WorkflowStageStatus="complete"|"current"|"upcoming"|"attention";
export interface ProjectWorkflowStage{id:string;label:string;status:WorkflowStageStatus}
export type TradeCoverageStatus="ready"|"collecting"|"needs-coverage"|"not-started";
export interface TradeBidStatus{id:string;trade:string;bidsReceived:number;status:TradeCoverageStatus}
export interface ProjectAttentionItem{id:string;title:string;message:string;severity:"warning"|"critical"|"info"}
export interface ProjectDetails{projectId:string;workflow:ProjectWorkflowStage[];trades:TradeBidStatus[];attention:ProjectAttentionItem[];activity:ActivityEvent[]}
export interface DocumentSourceReference{documentId:string;documentName:string;sheetNumber?:string;pageNumber?:number;sourceLabel:string}
export interface AIExtractedField{id:string;label:string;value:string;confidence:number;source?:DocumentSourceReference;editable:boolean}
export interface AITradeFinding{id:string;trade:string;confidence:number;sourceCount:number;status:"recommended"|"optional"}
export interface AIScopeObservation{id:string;category:"General"|"Architectural"|"Mechanical"|"Plumbing"|"Electrical"|"Fire Protection"|"Specifications";finding:string;confidence:number;source:DocumentSourceReference}
export interface AIRiskFinding{id:string;title:string;reason:string;severity:"Low"|"Medium"|"High";source?:DocumentSourceReference}
export interface AIPotentialExclusion{id:string;label:string;status:"Potential Exclusion"|"Needs Confirmation"}
export interface AIReviewData{projectId:string;status:"Analysis In Progress"|"Awaiting Documents"|"Ready for Human Review"|"Review Approved";documentsAnalyzed:number;drawingSheetsReviewed:number;findingsCount:number;attentionCount:number;overallConfidence:number;fields:AIExtractedField[];disciplines:string[];trades:AITradeFinding[];observations:AIScopeObservation[];risks:AIRiskFinding[];exclusions:AIPotentialExclusion[]}
export interface AIReviewApprovalState{projectInformation:boolean;requiredTrades:boolean;scopeObservations:boolean;riskItems:boolean;potentialExclusions:boolean}
export type ScopeItemCategory="Included Scope"|"Exclusion"|"Clarification"|"Allowance"|"Alternate"|"General Requirement";
export type ScopeItemReviewStatus="AI Generated"|"Reviewed"|"Human Revised"|"Human Added"|"Removed";
export type TradeScopeStatus="Draft"|"Needs Review"|"Ready for Approval"|"Approved"|"Human Revised";
export type BidPackageStatus="Not Generated"|"Draft"|"Ready for Review"|"Approved for Outreach";
export interface TradeScopeItem{id:string;tradeId:string;category:ScopeItemCategory;description:string;status:ScopeItemReviewStatus;confidence?:number;sources:DocumentSourceReference[];humanModified:boolean;originalDescription?:string;notes?:string}
export interface TradeScopeWarning{id:string;tradeId:string;message:string;reviewed?:boolean}
export interface TradeScopeDetail{id:string;projectId:string;trade:string;status:TradeScopeStatus;confidence:number;sourceCount:number;packageStatus:BidPackageStatus;items:TradeScopeItem[];warnings:TradeScopeWarning[];approvedBy?:string;approvedAt?:string}
export interface TradeScopeReview{scopeItems:boolean;exclusions:boolean;clarifications:boolean;sources:boolean}
export interface BidPackageDocument{documentId:string;documentName:string;included:boolean}
export interface BidPackageReviewState{tradeScope:boolean;exclusions:boolean;bidDeadline:boolean;documentList:boolean;submissionInstructions:boolean}
export interface BidPackage{id:string;projectId:string;tradeId:string;status:BidPackageStatus;requirements:string[];submissionInstructions:string[];documents:BidPackageDocument[]}
