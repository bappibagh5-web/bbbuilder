# Conceptual Production Data Model

## Modeling principles

This is a conceptual model, not a Django model definition. It establishes domain ownership, history, and relationships before implementation.

The production model should:

- be organization-aware from the start;
- distinguish stored binaries, logical documents, and immutable revisions;
- preserve analysis inputs and outputs by version;
- model provenance as first-class data;
- model material conflicts and their resolutions as first-class historical data;
- preserve extracted and human-accepted values separately;
- represent review, snapshot creation, and approval as records, not mutable booleans;
- use stable machine identifiers and codes while mapping user-facing labels in the UI;
- use PostgreSQL as the authoritative business store.

All mutable records should normally include an internal identifier, organization ownership where applicable, creation/update timestamps, and actors. Audit events supplement rather than replace domain history.

## Milestone 1 entities

### Organization

**Purpose:** Tenant boundary for data ownership and authorization. The initial organization is BB Builders Ltd.

**Important fields:** ID, legal/display name, slug, status, default timezone, created/updated timestamps.

**Relationships:** Has memberships, projects, file assets, analysis data, and audit events.

**Versioning:** Not versioned initially; material administrative changes are audited.

**Immutable versus editable:** ID and creation metadata are immutable. Name, status, and defaults are editable by authorized administrators.

### User

**Purpose:** Django-managed identity for a person using the system.

**Important fields:** ID, email or username identifier, display name, active state, staff/security attributes, last-login metadata.

**Relationships:** Has memberships; may create projects, upload files, review findings, approve intelligence, and cause audit events.

**Versioning:** No business version chain; authentication and material profile changes are audited where appropriate.

**Immutable versus editable:** ID is immutable. Identity attributes are controlled and editable subject to authentication policy. Passwords are never stored in plaintext.

### Membership / Role

**Purpose:** Connects a user to an organization and defines authorized behavior.

**Important fields:** ID, organization, user, role code (`admin`, `estimator_operator`, `viewer`), active state, effective dates.

**Relationships:** Belongs to one organization and user. Referenced when evaluating actions.

**Versioning:** Role changes should be historically auditable; implementation may use effective membership records or audit events.

**Immutable versus editable:** Organization/user association should not be repurposed; deactivate and create a new relationship when changing tenant identity. Role and status are editable by authorized administrators.

### Project

**Purpose:** Persistent bid-project workspace and aggregate root for Milestone 1.

**Important fields:** ID, organization, project number, name, client, address/location, project timezone, project type, status, bid deadline, questions deadline, description, created by, created/updated timestamps.

**Relationships:** Has contacts, documents, files, processing jobs, analysis runs, approvals, and audit events.

**Versioning:** The project record is editable with audit history. If later contractual baselines require snapshots, add explicit project versions rather than inferring them from audit logs.

**Immutable versus editable:** ID, organization, creator, and creation timestamp are immutable. Project metadata is editable by authorized users and auditable. Project number uniqueness should be scoped to the organization.

### ProjectContact

**Purpose:** Represents a project-specific contact and role without requiring external system access.

**Important fields:** ID, project, organization or company name, person name, email, phone, contact role/type, notes, active state.

**Relationships:** Belongs to a project; may later connect to a reusable Contact entity without conflating project-specific responsibility.

**Versioning:** Not versioned initially; changes are audited if material.

**Immutable versus editable:** ID/project association remain stable. Contact details and role are editable. Removal should usually deactivate rather than erase referenced history.

### FileAsset / ProjectFile

**Purpose:** Records an uploaded binary object independently of its business interpretation.

**Important fields:** ID, organization, project, storage provider, bucket, object key, original filename, detected and declared MIME types, byte size, checksum and algorithm, upload state, uploader, created timestamp, malware/validation state, encryption/storage metadata.

**Relationships:** Belongs to project and organization; referenced by a `DocumentRevision`; may have derived artifacts.

**Versioning:** Each uploaded binary is a new immutable asset. It is never replaced in place.

**Immutable versus editable:** Object identity, checksum, size, and original bytes are immutable after verified upload. Validation and lifecycle states may transition through controlled services. Display metadata may be corrected without changing the binary.

### Document

**Purpose:** Logical business document across revisions, such as “Architectural Drawing Set” or “Addendum 2.”

**Important fields:** ID, project, document type/category, title, discipline where known, status, and an explicit controlled `current_revision` reference.

**Relationships:** Belongs to a project; has one or more document revisions.

**Versioning:** The document is the stable identity; its content history lives in revisions. Current revision is not inferred from filename, issued date, revision label, or upload order.

**Immutable versus editable:** ID/project are immutable. Classification and title are editable with audit. Changing content always creates a revision. Changing `current_revision` is an explicit, validated backend transition and is audited. A newly uploaded revision does not automatically become current unless the defined revision workflow explicitly performs that transition.

### DocumentRevision

**Purpose:** Immutable business version of a logical document.

**Important fields:** ID, document, file asset, revision label/sequence, issued date if known, received date, source/addendum relationship, supersedes revision, processing eligibility, created by/time.

**Relationships:** Belongs to one document and file asset; has pages/sheets, processing jobs, and finding sources; may supersede another revision.

**Versioning:** Every new source version creates a new record. Revision ordering must not rely only on filenames.

**Immutable versus editable:** File association and source content are immutable. Human-entered labels may be corrected with audit, but a materially different file requires a new revision. Supersession is explicit.

### DocumentPage / DrawingSheet

**Purpose:** Addressable unit for viewing, indexing, extraction, and provenance.

**Important fields:** ID, document revision, page index, printed page label, detected sheet number/title, discipline, dimensions/orientation, extraction status, rendered-artifact reference.

**Relationships:** Belongs to one revision; supports finding sources; may reference derived render or OCR artifacts.

**Versioning:** Pages belong permanently to a specific revision. Reprocessing may create new extraction/index results without moving a page to another revision.

**Immutable versus editable:** Revision and page index are immutable. Detected labels and discipline may be corrected by humans while preserving the original detected values or correction history.

### ProcessingJob

**Purpose:** Durable record of asynchronous validation, extraction, rendering, classification, or analysis work.

**Important fields:** ID, organization/project, job type, target object, state, progress, input fingerprint, idempotency key, attempt count, queued/started/completed timestamps, error category/message, worker/task identifier, software/configuration version.

**Relationships:** Has exactly one strongly validated target appropriate to its job type. Milestone 1 targets may be a file asset, document revision, document page, analysis run, or analysis task run. A job may create derived artifacts, an analysis run, or task-run outputs.

**Versioning:** Each execution attempt or logical job is recorded. Retrying must not erase prior failure information.

**Immutable versus editable:** Identity, target, and input fingerprint are immutable. State and progress change through controlled transitions. Error records and timestamps are historical facts.

**Integrity constraint:** Implementation should avoid an unconstrained polymorphic `GenericForeignKey`. Prefer explicit nullable foreign keys with a database/service constraint requiring exactly one permitted target, separate job-target tables, or another design that preserves referential integrity. A processing job must not reference arbitrary domain records.

### AnalysisRun

**Purpose:** Versioned analysis of an explicit set of document revisions using recorded pipeline and AI configurations.

**Important fields:** ID, project, status, input manifest/fingerprint, included document revisions, pipeline version, model/provider identifiers, prompt/schema versions, started/completed timestamps, initiating user/job, predecessor run, summary metrics.

**Relationships:** Belongs to project; consumes document revisions; has analysis task runs; produces the overall analysis context from which task-level findings are generated.

**Versioning:** A changed input set, material pipeline change, or requested reanalysis creates a new run. Runs are never overwritten.

**Immutable versus editable:** Inputs and configuration snapshot become immutable when execution starts. Status changes through controlled transitions. Results remain attached to that run.

### AnalysisTaskRun

**Purpose:** Records one independently executable narrow AI or processing service within a complete analysis run. Examples include project facts, dates/bid conditions, document classification, sheet indexing, trade detection, scope observations, responsibility mapping, permits/inspections, landlord requirements, submittal/closeout requirements, risk/clarification detection, and conflict semantic comparison.

**Important fields:** ID, analysis run, task type, status, provider/model, prompt version, schema version, task-configuration version, input/source-reference manifest, started/completed timestamps, attempt count, error category/details, and usage/cost metadata when available.

**Relationships:** Belongs to one analysis run; may target an explicit subset of document revisions/pages/sources; produces findings or other typed task outputs; may have processing jobs.

**Versioning:** Each logical task execution and retry history is preserved. A retry may be represented as a new attempt record or a new task-run record according to the detailed job design, but prior errors and model/prompt configuration must remain traceable.

**Immutable versus editable:** Task type, analysis-run association, configuration snapshot, and resolved inputs become immutable when execution starts. Status, attempt, usage, error, and completion data transition through controlled services. Produced findings remain traceable to the exact successful task run.

### ExtractedFinding / ExtractedFact

**Purpose:** Structured proposed project intelligence produced by analysis or, if supported later, entered manually.

**Important fields:** ID, analysis run, producing analysis task run, category/type code, schema version, canonical structured value, display summary, confidence, materiality/risk flags, conflict indicator for convenient presentation, subject/reference key, predecessor or superseded-finding link, creation metadata.

**Relationships:** Belongs to an analysis run and is traceable to the analysis task run that produced it; has one or more sources and review records; may participate in one or more intelligence conflicts; may supersede other findings.

**Versioning:** AI-extracted content is immutable. Reanalysis creates new findings. Human edits are stored through review/accepted-value records rather than mutating the original extraction.

**Immutable versus editable:** Original extracted value, confidence, run association, and creation metadata are immutable. Derived conflict status may change through controlled consolidation/review processes, while history is preserved.

Recommended categories include project fact, required trade, scope observation, responsibility assignment, owner-supplied item, third-party scope, permit/inspection, landlord requirement, key date, bid condition, exclusion/clarification flag, submittal requirement, and closeout requirement.

### FindingSource / Provenance

**Purpose:** Connects a finding to the evidence supporting or contradicting it.

**Important fields:** ID, finding, document revision, page/sheet when available, source locator/label, evidence excerpt or bounded reference, region coordinates when available, relation (`supports`, `contradicts`, `qualifies`), extraction method, confidence.

**Relationships:** Belongs to a finding and source revision; optionally references a page/sheet. Several sources may support one finding.

**Versioning:** Provenance produced by a run is immutable. Corrected provenance should be added as a reviewed correction or through a new run, not silently rewritten.

**Immutable versus editable:** Source associations and machine evidence are immutable. Human annotations may be appended with authorship and timestamps.

### IntelligenceConflict

**Purpose:** Represents a material contradiction or disagreement between findings and/or provenance sources that requires explicit human resolution. A finding-level conflict indicator alone is insufficient.

**Important fields:** ID, project, analysis run, conflict type, materiality, status, explanation, detection confidence, resolution outcome, resolution rationale, resolved by, resolved at, and supersedes/previous-resolution relationship where appropriate.

**Relationships:** Belongs to a project and analysis run. References two or more participating findings and/or finding sources through explicit join relationships. May be identified by an analysis task run. Resolution is considered when producing an intelligence snapshot.

**Versioning:** Detection and participating claims are preserved. Resolution is historical and auditable. A changed resolution creates a new resolution/conflict version that explicitly supersedes the earlier decision rather than overwriting it.

**Immutable versus editable:** Participating claims and initial detection record are immutable after creation. Status follows controlled transitions. Submitted resolution outcome, rationale, actor, and timestamp are immutable; corrections create a superseding record.

**Example:** One drawing states a March 31 bid deadline and an addendum states April 2. Both findings and sources remain preserved. The conflict connects the claims, and a human resolution determines the effective reviewed value used in the snapshot.

### FindingReview

**Purpose:** Records a human decision and, when applicable, the accepted corrected value.

**Important fields:** ID, finding, reviewer membership/user, outcome, original-value reference, accepted value, rationale/comment, reviewed timestamp, supersedes review.

**Relationships:** Belongs to a finding; may supersede an earlier review; is considered by project intelligence approval.

**Versioning:** Reviews are append-only decisions. A changed decision creates a new review linked to the prior record.

**Immutable versus editable:** Submitted decisions are immutable. Draft UI state need not be persisted as a final review. Corrections require a new record.

### ProjectIntelligenceSnapshot

**Purpose:** Immutable manifest of the effective reviewed project intelligence at a specific point after finding review and material-conflict resolution. It is the approval target; an analysis run alone cannot identify post-extraction human decisions.

**Important fields:** ID, project, source analysis run, included finding IDs, effective finding-review IDs, relevant resolved intelligence-conflict IDs, manifest/schema version, canonical manifest or manifest reference, cryptographic hash, created by, and creation timestamp.

**Relationships:** Belongs to a project and source analysis run; references the exact included findings, effective reviews, and conflict resolutions. Has zero or more project intelligence approval records.

**Versioning:** Every materially different effective reviewed state creates a new immutable snapshot and version/hash. Snapshots are never edited in place.

**Immutable versus editable:** The complete manifest, membership, version, hash, creator, and creation time are immutable. A correction requires a new snapshot.

### ProjectIntelligenceApproval

**Purpose:** Final human approval of an immutable project intelligence snapshot for controlled downstream consumption.

**Important fields:** ID, project, project intelligence snapshot, approval status, approver, approved timestamp, approval note, supersedes/revokes approval, readiness-check result.

**Relationships:** Belongs to a project and references exactly one immutable project intelligence snapshot.

**Versioning:** Every approval, revocation, or replacement is a separate record. New material revisions do not mutate the previous approval.

**Immutable versus editable:** Submitted approval facts are immutable. A newer approval may supersede an older one explicitly.

### AuditEvent

**Purpose:** Append-oriented record of security-sensitive and business-significant actions.

**Important fields:** ID, organization, actor or system identity, action code, target type/ID, project when applicable, UTC timestamp, request/correlation ID, contextual metadata, before/after references where safe, source IP/user agent subject to policy.

**Relationships:** May refer to any domain object; belongs to an organization.

**Versioning:** Append-only.

**Immutable versus editable:** Immutable after creation through ordinary application paths. Retention/access policy remains to be decided.

## Key Milestone 1 relationships

```text
Organization 1 ── * Membership * ── 1 User
Organization 1 ── * Project
Project 1 ── * ProjectContact
Project 1 ── * FileAsset
Project 1 ── * Document 1 ── * DocumentRevision 1 ── * DocumentPage
DocumentRevision * ── 1 FileAsset
Project/Revision/Page 1 ── * ProcessingJob
Project 1 ── * AnalysisRun * ── * DocumentRevision
AnalysisRun 1 ── * AnalysisTaskRun 1 ── * ExtractedFinding
ExtractedFinding 1 ── * FindingSource
DocumentRevision/Page 1 ── * FindingSource
ExtractedFinding 1 ── * FindingReview
IntelligenceConflict * ── * ExtractedFinding/FindingSource
Project 1 ── * ProjectIntelligenceSnapshot 1 ── * ProjectIntelligenceApproval
Organization/Project 1 ── * AuditEvent
```

## Structured values and schema evolution

Findings vary by category. Avoid forcing every value into one free-text field. Use a typed JSON payload validated against a versioned schema or category-specific normalized tables where querying and integrity require them. Record the schema version with every finding. Human-accepted values must follow the same validation rules.

Responsibility findings should represent supply, installation, GC coordination/support, and third-party responsibility independently. Dates should distinguish date-only values from instants and carry the project timezone context.

## Future entities — described, not implemented in Milestone 1

| Entity | Future purpose and important separation |
|---|---|
| Trade | Canonical construction discipline; separate from schedule tasks and company capability. |
| ScopeItem | Discrete requirement with provenance and split responsibilities. |
| TradePackage | Approved project-specific collection of scope items and RFQ documents. |
| Subcontractor | Company/business entity, separate from people and project relationships. |
| Contact | Person/contact method, potentially associated with multiple companies over time. |
| TradeCapability | Company-to-trade capability with geography, qualification, and evidence. |
| BidInvitation | Controlled invitation from a trade package to a project subcontractor relationship. |
| BidSubmission | Received quotation envelope and metadata, separate from its revisions. |
| QuoteVersion | Immutable commercial revision with price, scope, alternates, allowances, exclusions, taxes, and attachments. |
| BidComparison | Versioned deterministic normalization and leveling snapshot. |
| Award | Human selection/award record; not inferred from lowest price. |
| PurchaseOrder | Versioned contractual commitment following authorization. |
| Proposal | Logical client proposal for a project. |
| ProposalVersion | Immutable proposal/revision with deterministic pricing inputs and terms. |
| ScheduleTask | Individual construction activity; many tasks may relate to one trade. |
| Submittal | Logical submittal package. |
| SubmittalRevision | Immutable revision and review cycle, including outcomes such as Reviewed as Noted or Revise and Resubmit. |
| ComplianceDocument | Insurance, safety, license, or other compliance evidence with expiry/review state. |
| CloseoutRequirement | Required closeout deliverable, responsibility, due state, revisions, and approval. |

These future entities may be referenced by conceptual identifiers or extension points only when necessary. Their workflows, tables, endpoints, and UI are not Milestone 1 deliverables.
