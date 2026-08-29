# BB Builders Current Development Status

## Project

BB Builders AI Bid Automation System

## Current milestone

Milestone 1 — Production Foundation, Project Intake & AI Drawing/Document Review

## Current implementation status

The approved frontend demo already exists.

Permanent project documentation exists under `/docs`.

M1-01 — Backend & Local Development Foundation is **complete**.

M1-02 — Organization, Users, Authentication & Permissions is **complete**. Automated and manual local authentication validation passed on August 29, 2026.

M1-01 currently includes:

- Django 5.2 backend
- Django REST Framework
- PostgreSQL
- Redis
- Celery foundation
- S3-compatible storage foundation
- MinIO for local development
- Environment-specific Django settings
- `/api/v1/health/` endpoint
- Backend tests and linting
- Docker Compose local infrastructure
- Local setup documentation

Local development topology:

| Service | Address |
|---|---|
| Next.js | `127.0.0.1:3000` |
| Django | `127.0.0.1:8000` |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |
| MinIO API | `127.0.0.1:9000` |
| MinIO Console | `127.0.0.1:9001` |

Docker infrastructure was manually verified on August 29, 2026:

- PostgreSQL healthy
- Redis healthy
- MinIO healthy
- Django migrations successfully applied
- Django local server successfully started using `config.settings.local`

M1-02 currently includes:

- Custom email-based Django user model
- Organization and organization-specific membership models
- Admin, Estimator / Operator, and Viewer role codes
- Active/effective membership enforcement helpers
- Reusable DRF organization permission classes
- CSRF-protected Django session login and logout
- `/api/v1/auth/csrf/`, `/login/`, `/logout/`, and `/me/` endpoints
- Django Admin registration for users, organizations, and memberships
- Idempotent organization-membership bootstrap command
- Minimal Next.js login page, authenticated route gate, session-expiry handling, and logout
- Backend identity, session, CSRF, membership, role, and cross-organization tests

The existing Next.js workflow screens continue to use deterministic demo fixture data. No production project or domain functionality has been connected yet.

## Completed implementation tasks

### M1-01 — Backend & Local Development Foundation

- Git commit: `2023d74264a65594eb751e1e40f23a13edfc0c7f`
- Commit message: `feat: establish milestone 1 backend development foundation`
- Branch at commit: `master`
- GitHub push status: pushed to `origin/master`

### M1-02 — Organization, Users, Authentication & Permissions

- Status: complete
- Automated validation: passed
- Manual local authentication validation: passed using `http://127.0.0.1:3000` and `http://127.0.0.1:8000`
- M1-03 status: next / not started
- Important local migration note: the M1-01 PostgreSQL volume contains migrations from before the custom user model existed. It must be reset once using the documented development reset procedure before applying M1-02 migrations. The repository does not reset it automatically.

## Next implementation task

M1-03 — Project Production Data Model & API. M1-03 is next and has not started; begin it only after explicit approval.

Do not jump directly into project, document, or AI implementation before completing the planned task sequence.

## Planned Milestone 1 task sequence

1. M1-01 — Backend & Local Development Foundation
2. M1-02 — Organization, Users, Authentication & Permissions
3. M1-03 — Project Production Data Model & API
4. M1-04 — Connect Projects UI to Backend
5. M1-05 — File / Document Storage Model
6. M1-06 — Production Upload Workflow
7. M1-07 — Document Processing Pipeline
8. M1-08 — PDF Page / Sheet Indexing
9. M1-09 — Structured AI Analysis
10. M1-10 — Provenance, Findings & Human Review
11. M1-11 — Intelligence Snapshot, Approval & Audit
12. M1-12 — Real BB Builders Project Validation & Milestone Polish

## Source of truth

Before making changes, a new engineer or AI session must read:

1. `docs/PROJECT_CONTEXT.md`
2. `docs/REAL_WORKFLOW.md`
3. `docs/DATA_MODEL.md`
4. `docs/MILESTONE_1_SPEC.md`
5. `docs/AI_DOCUMENT_PIPELINE.md`
6. `docs/BUSINESS_RULES.md`
7. `docs/DECISIONS.md`
8. `docs/CURRENT_STATUS.md`
9. `README.md`
10. Recent Git history

The repository and documentation are authoritative. Do not rely on assumptions from a previous chat.

## Historical project evidence

The architecture and workflow were validated against real BB Builders historical materials, including:

- Client RFP/tender packages
- Construction drawings
- Trade lists
- Subcontractor quotations
- Quote revisions and alternates
- Subcontractor awards and purchase orders
- BB Builders RFQ templates
- Scope clarification documents
- GC estimate/proposal revisions
- Client approval and purchase order
- Construction schedule and Smartsheet export
- Submittal revision/review workflows
- Closeout documents

The actual historical source files are not stored in this repository unless explicitly added later.

## Important working rule

After every implementation task:

1. Validate.
2. Review.
3. Commit.
4. Push to GitHub.
5. Update `CURRENT_STATUS.md` if development state materially changed.
6. Only then begin the next task.

Do not implement multiple Milestone 1 tasks in one uncontrolled change.

# Forward Development Roadmap

The purpose of this roadmap is to let a future engineer or AI session understand not only where development stopped, but also the intended implementation sequence and boundaries ahead.

## Milestone 1 — Current active milestone

**Production Foundation, Project Intake & AI Drawing/Document Review**

**Status:** In progress

### Primary acceptance journey

```text
Authenticated user
  → create persistent project
  → upload real tender documents
  → preserve immutable originals
  → process documents
  → index PDF pages/sheets
  → structured AI analysis
  → source provenance
  → human review
  → conflict resolution
  → immutable intelligence snapshot
  → approval
  → persistent state after logout/reload
```

### Planned task sequence

#### M1-01 — Backend & Local Development Foundation

**Status:** Complete

**Purpose:** Establish Django/DRF, PostgreSQL, Redis, the Celery foundation, S3-compatible storage foundation, local MinIO, environment configuration, a health endpoint, testing, and local infrastructure.

#### M1-02 — Organization, Users, Authentication & Permissions

**Status:** Complete

**Purpose:** Create the organization-aware BB Builders identity and access foundation.

Expected scope:

- Organization
- Django user and authentication foundation
- Membership
- Roles: Admin, Estimator / Operator, and Viewer
- Secure browser authentication
- Authenticated API boundary
- Server-enforced permissions
- Initial administration through Django Admin where practical

Do not build custom user-management UI unless required.

#### M1-03 — Project Production Data Model & API

**Status:** Next / Not started

**Purpose:** Replace project fixture concepts with persistent organization-owned project data.

Expected scope:

- Project
- ProjectContact
- Project timezone
- Deadlines
- Project number
- Client and location metadata
- Project status
- Audit events
- DRF project APIs
- Permission enforcement

#### M1-04 — Connect Projects UI to Backend

**Status:** Planned

**Purpose:** Connect the approved Next.js project workflow to real APIs.

Expected scope:

- Project directory
- Project creation
- Project detail and overview
- Persistent edit state
- Loading, error, and permission states
- Remove the Milestone 1 dependency on project fixture data

Do not redesign the approved frontend unnecessarily.

#### M1-05 — File & Document Domain Foundation

**Status:** Planned

**Purpose:** Create the persistent file, document, and revision architecture.

Expected scope:

- FileAsset
- Document
- DocumentRevision
- Explicit current revision
- Immutable originals
- Checksums and metadata
- Processing eligibility
- Revision history
- Basic source-document access controls

#### M1-06 — Production Upload Workflow

**Status:** Planned

**Purpose:** Replace simulated browser file selection with real secure uploads.

Expected scope:

- Upload intents
- Private S3-compatible storage
- MinIO local implementation
- Upload verification
- MIME and size validation
- Checksums
- Durable upload state
- Revision creation
- Retry and error behavior

#### M1-07 — Document Processing Pipeline

**Status:** Planned

**Purpose:** Establish durable asynchronous processing.

Expected scope:

- ProcessingJob
- Celery execution
- Redis broker
- Idempotency
- Retries and failure states
- File classification
- Format-specific extraction foundation
- PDF, DOCX, XLSX, and image processing adapters

PDF remains the highest priority.

#### M1-08 — PDF Page & Drawing Sheet Indexing

**Status:** Planned

**Purpose:** Create source-addressable construction-document structure.

Expected scope:

- DocumentPage / DrawingSheet
- PDF page extraction
- Rendering
- Page labels
- Sheet number and title detection
- Discipline classification
- Source preview and navigation support
- Processing provenance

#### M1-09 — Structured AI Analysis

**Status:** Planned

**Purpose:** Turn processed tender packages into structured proposed project intelligence.

Expected categories:

- Project facts
- Drawing disciplines
- Required trades
- Scope observations
- Responsibility assignments
- Owner-supplied items
- Third-party scope
- Permits and inspections
- Landlord requirements
- Key dates
- Bid conditions
- Exclusions and clarifications
- Discovered submittal requirements
- Discovered closeout requirements

Architecture:

```text
AnalysisRun
  → AnalysisTaskRun
  → structured findings
```

AI must use narrow, schema-validated services.

#### M1-10 — Provenance, Findings, Conflict & Human Review

**Status:** Planned

**Purpose:** Make AI results reviewable and auditable.

Expected scope:

- ExtractedFinding
- FindingSource / provenance
- Confidence and risk display
- IntelligenceConflict
- Accepted
- Edited / Accepted
- Rejected
- Needs Clarification
- Historical FindingReview records
- Human conflict resolution

Original AI values must never be overwritten by human edits.

#### M1-11 — Intelligence Snapshot, Approval & Audit

**Status:** Planned

**Purpose:** Create the controlled output of Milestone 1.

Expected scope:

- ProjectIntelligenceSnapshot
- Deterministic readiness rules
- ProjectIntelligenceApproval
- Append-oriented audit events
- Re-review behavior after material revision
- Preservation of previous approved snapshots

Only approved intelligence becomes eligible for later bidding workflows.

#### M1-12 — Real BB Builders Project Validation & Milestone Polish

**Status:** Planned

**Purpose:** Validate the completed milestone using representative BB Builders historical material.

Expected validation:

- Real or sanitized tender-package upload
- Mixed documents
- Large construction PDF
- Page and sheet indexing
- Structured findings
- Source provenance
- Deliberate conflict
- Human review
- Approval
- Persistence after reload
- Permissions
- Error and retry handling

Use the historical BB Builders / JD Sports material as workflow evidence, subject to access and privacy requirements.

Milestone 1 ends after successful validation and a client-ready demonstration.

## Milestone 2 — Future

**Trade Scope Builder, RFQ Packages & Contractor Discovery**

High-level goals only:

```text
Approved project intelligence
  → structured trade scopes
  → human scope approval
  → RFQ/trade packages
  → BB Builders subcontractor database
  → existing-network search first
  → external contractor discovery for coverage gaps
  → qualification and deduplication
  → approved outreach recipient lists
```

Important future concepts:

- Trade
- ScopeItem
- TradePackage
- Subcontractor
- Contact
- TradeCapability
- Project-specific contractor relationship

Do not implement during Milestone 1.

## Milestone 3 — Future

**Outreach, Bid Intake, Qualification & Bid Leveling**

High-level goals only:

```text
Approved RFQ
  → subcontractor invitations
  → campaign tracking
  → inbound quote association
  → QuoteVersion
  → AI-assisted quote extraction
  → exclusions, alternates, and allowances
  → scope coverage
  → normalization
  → intelligence and clarification flags
  → human bid selection
```

Important principle: Lowest submitted price is not automatically the best commercial bid.

Historical BB Builders data proves the system must support:

- Quote revisions
- Alternate materials
- Added options
- Permits
- Taxes
- Scope differences
- Awarded values different from initial quote values

Do not implement during Milestone 1.

## Milestone 4 — Future

**Final Client Proposal & Award Workflow**

High-level goals only:

```text
Approved trade selections
  → deterministic pricing and markup
  → Proposal
  → ProposalVersion
  → human approval
  → client-facing output
  → award
  → subcontractor purchase orders
  → compliance and document requests
```

Important principles:

- Pricing arithmetic is deterministic application logic.
- Proposal revisions are immutable and versioned.
- Commercial history is never silently overwritten.
- Awards are human decisions.

Do not implement during Milestone 1.

## Milestone 5 — Future

**Smartsheet / Project Management Integration**

High-level goals only:

```text
Awarded project
  → approved schedule/template
  → construction activities
  → trade dates
  → milestones
  → inspections
  → delivery dates
  → Smartsheet synchronization
```

Historical BB Builders schedules show:

- One trade may have multiple separate schedule tasks.
- Overlapping activities are normal.
- Schedule task and trade are separate concepts.

Do not build a full standalone construction-management platform as part of the current approved scope.

## Future expansion — Not current contract scope

Historical BB Builders documents reveal possible future modules:

- Submittal management
- Submittal revision and review workflow
- Compliance tracking
- Change orders
- Subcontractor invoices and progress claims
- Contract-value tracking
- Closeout requirements
- Warranties
- O&M manuals
- As-built collection
- Client closeout packages
- Subcontractor performance and history

These are future opportunities only.

They must **not** be silently included in the current $5,000 core project unless separately agreed.

## Development control rule

For every task:

1. Read the permanent documentation.
2. Confirm the current task and its boundaries.
3. Implement only that task.
4. Run tests and validation.
5. Review the diff.
6. Do not proceed automatically.
7. Commit approved work.
8. Push to GitHub.
9. Update `CURRENT_STATUS.md` when status materially changes.
10. Begin the next task only after explicit approval.

Never implement multiple roadmap tasks in one uncontrolled Codex request.

## Recovery instruction

If all previous ChatGPT or Codex conversations are lost, a new session should:

1. Open the repository.
2. Read every file under `/docs`.
3. Read `docs/CURRENT_STATUS.md`.
4. Read `README.md`.
5. Inspect recent Git history.
6. Identify the last completed task.
7. Report its understanding.
8. Ask for approval before changing code.

The repository, documentation, and Git history are the authoritative project memory.
