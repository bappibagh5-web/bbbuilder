# Milestone 1 Technical Specification

## Milestone

**Production Foundation, Project Intake & AI Drawing/Document Review**

## Objective

Deliver a production foundation in which an authorized BB Builders user can create a persistent bid project, upload and preserve a mixed tender package, monitor background processing, review structured AI-assisted project intelligence with source provenance, resolve uncertainty or conflict, and approve an immutable project intelligence snapshot.

The existing frontend demonstration is the approved UX baseline. Implementation should retain its navigation, information architecture, and review patterns wherever practical while replacing fixtures and simulations with authenticated APIs and persistent state.

## Scope

### Production foundation

- Django and Django REST Framework service
- PostgreSQL persistence
- Organization-aware users, memberships, and roles
- Secure browser authentication managed by Django
- Versioned API boundary for the existing frontend
- S3-compatible private object storage
- Celery and Redis background processing
- Server-side audit events
- Environment-specific configuration and secret handling

### Project intake

- Create, view, and edit organization-owned projects
- Persist project number, name, client, location, project timezone, contacts, relevant deadlines, and basic metadata
- Enforce role-based access and organization boundaries
- Provide stable project identifiers for frontend workspace routes
- Audit project creation and material metadata changes

### Documents and revisions

- Upload multiple files from supported bid packages
- Validate declared and detected file properties
- Preserve original files immutably in private storage
- Record checksum, file size, MIME type, uploader, and upload state
- Create logical documents and immutable document revisions
- Preserve prior revisions and explicit supersession
- Display durable upload and processing states
- Support PDF, DOCX, XLSX, and JPG/PNG intelligent processing
- Retain other permitted source files without promising intelligent parsing

### AI-assisted review

- Classify files and drawing disciplines
- Extract text/metadata and index document pages/drawing sheets
- Produce schema-validated structured findings
- Consolidate findings across documents
- retain provenance, confidence, analysis-run identity, and conflict information
- Support human review outcomes: Accepted, Edited / Accepted, Rejected, Needs Clarification
- Support final project-intelligence approval by an authorized user
- Preserve prior analysis and approval history following document revisions

## Primary acceptance journey and delivery priority

The primary Milestone 1 acceptance journey is:

```text
Authenticated user
  → create persistent project
  → upload real tender documents
  → preserve original files and revision history
  → process documents
  → index PDF pages and construction sheets
  → run structured AI analysis
  → retain provenance
  → complete human finding review
  → resolve material intelligence conflicts
  → create an immutable ProjectIntelligenceSnapshot
  → approve that snapshot
  → confirm state survives logout and reload
```

PDF construction-document intelligence is the highest-priority processing capability. PDF must receive full drawing/document indexing and targeted construction intelligence. DOCX, XLSX, and JPG/PNG remain supported input types, but they may use format-appropriate text, table, metadata, OCR, or image extraction and do not need identical drawing-level analysis depth.

Production security, backups, logging, and monitoring require a safe baseline. The milestone should implement them proportionally to this acceptance journey rather than allowing advanced operational tooling to displace the core workflow.

## User roles

- **Admin:** Manages organization access and may perform all Milestone 1 project/review actions.
- **Estimator / Operator:** Creates and edits projects, uploads documents, initiates processing as allowed, reviews findings, and may create and approve intelligence snapshots.
- **Viewer:** Reads authorized project, document, finding, and approval information without mutation rights.

Admin and Estimator / Operator memberships may create and approve intelligence snapshots. Self-approval is permitted because the contracted checkpoint requires explicit human intent but not segregation of duties. Viewer memberships remain read-only.

## User stories

### Access and organization

- As an authorized BB Builders user, I can log in securely and access only projects belonging to my organization.
- As an administrator, I can control initial user membership and roles.
- As a viewer, I cannot make changes by directly calling an API that the UI hides.

### Project intake

- As an estimator, I can create a project with required metadata and an explicit timezone.
- As an estimator, I can correct project metadata and see that material changes are audited.
- As a user, I can return later and see the same persistent project state.

### Documents

- As an estimator, I can select and upload a mixed set of supported tender files.
- As a user, I can see validation, upload, processing, completion, review-needed, and failure states.
- As an estimator, I can add a new revision without overwriting the original.
- As a user, I can distinguish the logical document, each revision, and the current/superseded state.
- As a user, I can access an authorized source document and navigate to a referenced page or sheet when available.

### Analysis

- As an estimator, I can initiate or observe analysis of the selected document-revision set.
- As a user, I can see structured project facts, trades, scope findings, responsibilities, owner/third-party items, permits, landlord requirements, dates, bid conditions, clarification flags, and discovered submittal/closeout requirements.
- As a reviewer, I can see the source and confidence for every important finding.
- As a reviewer, I can see when sources conflict instead of receiving an unexplained chosen value.

### Human review and approval

- As a reviewer, I can accept, edit and accept, reject, or mark a finding as needing clarification.
- As a reviewer, I can preserve the original extracted value when accepting an edit.
- As an approver, I can see whether the intelligence set is ready for approval and what remains unresolved.
- As an approver, I can approve a defined immutable `ProjectIntelligenceSnapshot` containing the effective findings, reviews, and conflict resolutions.
- As a user, I can see who reviewed and approved information and when.
- As a reviewer, I am prompted to re-review materially affected information after new document revisions or analysis.

## Functional requirements

### FR-1 Authentication and authorization

- Django authenticates users using the secure browser mechanism selected by ADR.
- Every protected API enforces membership, organization ownership, and role permissions.
- Authentication secrets are not stored in browser local storage.
- Login, logout, expiry, unauthorized, and forbidden states are handled by the frontend.

### FR-2 Project management

- Project creation validates organization-scoped project-number uniqueness and required fields.
- Project timezone is mandatory.
- Date-only and datetime values are represented unambiguously in APIs.
- Project lists and details support the approved frontend views.
- Changes create appropriate audit events.

### FR-3 Upload and storage

- Uploads use an authorized, scalable mechanism appropriate for private S3-compatible storage.
- The backend creates and controls file records and upload authorization.
- Completion is verified by the backend before a file becomes processable.
- Checksum, size, detected MIME type, storage key, and uploader are persisted.
- Invalid, incomplete, unsafe, or disallowed files do not enter normal processing.
- Original object keys cannot be replaced by uploading a new revision.

### FR-4 Document and revision management

- Users can classify or correct logical document metadata.
- Each source change creates a document revision.
- The system displays revision history and supersession.
- Analysis inputs name exact revision IDs.
- Unsupported intelligent formats have a clear retained-but-not-processed state.

### FR-5 Processing

- Each asynchronous operation has a durable processing-job record.
- Jobs have controlled states, progress where meaningful, retry/error details, and idempotency protection.
- Worker retries do not create uncontrolled duplicate documents, runs, or findings.
- The UI can recover current state after reload without relying on an open browser timer.

### FR-6 Indexing and extraction

- Supported documents produce text and metadata where technically available.
- PDF pages are indexed; construction sheets receive detected number/title/discipline where possible.
- Scanned/image documents can be routed to appropriate visual/OCR processing.
- Extracted and derived artifacts remain associated with their source revision and processing version.

### FR-7 Structured analysis

- AI output validates against versioned schemas.
- Analysis uses narrow services for classification, facts, trades, responsibilities, conditions, and other categories.
- Each analysis run records its complete input set and pipeline version.
- Each narrow AI or processing service execution has an `AnalysisTaskRun` recording task type, source inputs, provider/model, prompt/schema/configuration versions, attempts, errors, timestamps, and available usage/cost metadata.
- Findings are traceable to the analysis task run that produced them.
- Invalid AI output is rejected or repaired through controlled processing and never treated as approved truth.

### FR-8 Provenance and conflict

- Material findings retain one or more source links.
- Source links identify document revision and page/sheet when possible.
- Evidence that cannot be precisely located is labeled accordingly.
- Consolidation detects plausible contradiction or material disagreement and creates a first-class `IntelligenceConflict` referencing all participating findings and/or provenance sources.
- The system does not silently resolve conflicting sources.
- Conflict resolutions preserve outcome, rationale, resolver, timestamp, and superseded resolution history.

### FR-9 Review and approval

- Finding decisions are persisted with reviewer and UTC timestamp.
- Edited acceptance preserves machine and accepted human values.
- Submitted review decisions are historical records rather than overwritten flags.
- After review and conflict resolution, the backend creates an immutable `ProjectIntelligenceSnapshot` manifest containing the analysis run, included findings, effective finding reviews, relevant resolved conflicts, version, and hash.
- Final approval references exactly one immutable project intelligence snapshot; an analysis run by itself is not approvable.
- Approval readiness is calculated by deterministic server logic.
- New material revisions do not mutate prior approvals.

### FR-10 Audit trail

- Project, upload, revision, processing, review, approval, and authorization-sensitive actions produce server-side audit events.
- Automated events identify the responsible service/job and initiating context.
- The project activity experience can read production audit events, even if the complete activity UI is staged later within the milestone.

## Non-functional requirements

### Security

- Private-by-default storage and authorized access
- Server-enforced object and organization permissions
- CSRF/CORS/session controls appropriate to the selected topology
- File validation and a documented malware-scanning posture
- Secrets held outside source control and frontend bundles
- No sensitive content in routine logs or client-visible errors

### Reliability and integrity

- Database transactions for important transitions
- Idempotent asynchronous processing
- Explicit failure and retry states
- Checksums for uploaded assets
- No silent overwrite of source, findings, reviews, or approvals
- Backup and recovery plan before production launch

### Performance and scale

- Direct or multipart object-storage upload where selected by ADR
- Background processing for expensive document/AI work
- Pagination for project, document, finding, and audit collections
- Bounded file/page processing and configurable limits
- Avoid loading entire tender packages into frontend memory

### Auditability and observability

- UTC event timestamps and correlation IDs
- Structured application and worker logging
- Processing metrics and failure alerts
- Traceability from approved finding to analysis run and source revision

### Maintainability

- Versioned API and finding schemas
- Domain modules with tested service boundaries
- API contract or generated-client strategy
- Automated backend, frontend integration, and end-to-end tests
- Architecture decisions documented before high-cost commitments

### Accessibility and responsive UX

- Preserve current responsive baseline
- Keyboard-operable review and upload controls
- Semantic labels and perceivable processing/error status
- No workflow depends only on color

## Acceptance criteria

Milestone 1 is acceptable when all of the following are demonstrated in a production-like environment:

1. An authenticated BB Builders member can create and later reopen a persistent project.
2. Unauthorized organization access is denied at the API layer.
3. Project timezone and deadlines round-trip without date shifting.
4. A user can upload a representative mixed package containing PDF, DOCX, XLSX, and image files.
5. Original binaries remain privately stored and checksum-verifiable.
6. Uploading a replacement creates a visible new revision while the prior revision remains accessible to authorized users.
7. Durable processing states survive refresh and worker restart/retry scenarios.
8. A representative PDF drawing set receives a navigable page/sheet index.
9. Analysis returns schema-valid structured findings across the required intelligence categories.
10. Important findings link to their document revision and page/sheet where possible.
11. A deliberate cross-document conflict is surfaced for human resolution.
12. Low confidence is visibly flagged but does not automatically accept or reject a finding.
13. A reviewer can exercise all four review outcomes and the decisions persist.
14. Edited / Accepted displays both original and accepted values.
15. Final approval is blocked according to the agreed readiness policy when material unresolved items remain.
16. The system creates an immutable, hashable intelligence snapshot from the exact included findings, effective reviews, and relevant conflict resolutions.
17. An authorized approver can approve that exact snapshot, and the approval cannot drift if later reviews or analysis occur.
18. A new material document revision preserves the old approved snapshot and creates required re-review work.
19. Project, upload, processing, review, conflict resolution, snapshot creation, and approval actions are represented in the audit trail.
20. State and permissions remain correct after logout, login, and page reload.
21. The existing approved frontend remains recognizable and operational with real API state.
22. Automated tests cover permissions, immutable file/revision preservation, idempotent jobs, provenance, finding review history, conflict resolution, snapshot approval, and re-review after material revision.
23. One representative real or sanitized BB Builders tender package completes the entire primary acceptance journey in a production-like environment.

## Explicitly out of scope

- Live contractor discovery
- Outbound RFQ email campaigns and follow-ups
- Inbound email bid ingestion
- Real quote normalization or bid leveling
- Trade selection and awards
- GC proposal generation or PDF production
- Client proposal approval/e-signature
- Purchase orders
- Smartsheet or n8n workflow implementation
- Change orders and invoicing/progress claims
- Submittal management
- Construction schedule management
- Compliance and closeout management
- DWG/CAD intelligent parsing
- Custom user/organization administration UI beyond the basic capability needed for the initial organization; Django Admin may be used initially
- Advanced observability dashboards and enterprise-grade support tooling
- Complex retention automation or elaborate backup-management UI
- Sophisticated historical-data migration unless separately approved

## Dependencies and prerequisites

- At least one representative real or sanitized BB Builders tender package for the primary acceptance demonstration
- Confirmed project metadata requirements and role permissions
- Authentication ADR
- Hosting and networking decision
- S3/Spaces environment configuration
- Upload and malware-scanning decision
- PostgreSQL and Redis environments
- OpenAI account, data-handling approval, task evaluation set, and model selection
- Approval-readiness and material-change policy
- Operational logging, monitoring, and backup choices

## Risks

- Poor or inconsistent source documents may limit extraction and sheet detection.
- Cross-document conflicts can be ambiguous and require domain-specific human interpretation.
- AI confidence values may be poorly calibrated without representative evaluation data.
- Large drawing packages can create cost, latency, memory, and timeout pressure.
- Auth/domain topology choices can cause late CSRF/CORS rework.
- Treating fixture types as final database models could encode display-oriented assumptions.
- Inadequate revision semantics could undermine auditability.
- A generic AI prompt could produce inconsistent, difficult-to-validate data.
- Lack of malware and file-limit decisions can block production upload launch.
- Expanding into later procurement or proposal features would jeopardize Milestone 1 focus.

## Implementation stages

1. **Architecture baseline:** ADRs, environments, Django/DRF foundation, CI and health checks.
2. **Identity and tenancy:** users, organization, memberships, roles, authentication, permission tests; Django Admin may provide initial basic user/membership administration.
3. **Persistent projects:** project/contact models and APIs; connect project list/create/overview frontend.
4. **Storage foundation:** file assets, secure upload, validation, checksum, access, and revision model.
5. **Processing orchestration:** Celery/Redis jobs, durable state, retries, idempotency, observability.
6. **Document extraction/indexing:** supported format handlers, PDF pages/sheets, derived artifacts.
7. **Structured intelligence:** analysis-run, analysis-task-run, and finding schemas; task-specific AI services and provenance.
8. **Consolidation/conflicts:** cross-document reconciliation, first-class conflict records, and historical resolution.
9. **Human review:** review outcomes, accepted edits, immutable intelligence snapshots, approval readiness, snapshot approval, and audit.
10. **Frontend completion:** replace remaining Milestone 1 fixtures, add error/retry/conflict/revision states.
11. **Production readiness:** proportional security, backup, logging, and monitoring baselines; performance limits; automated invariant tests; and end-to-end demonstration with a representative BB Builders package.

See [AI_DOCUMENT_PIPELINE.md](./AI_DOCUMENT_PIPELINE.md) for the processing design and [BUSINESS_RULES.md](./BUSINESS_RULES.md) for invariant behavior.
