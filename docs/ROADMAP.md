# BB Builders Contracted Delivery Roadmap

## 1. Purpose

This is the canonical full delivery roadmap for the **BB Builders Ltd. AI-Powered Bid Automation System**. It preserves the approved commercial baseline, milestone boundaries, dependency flow, and planned engineering decomposition so the project can be recovered without conversation history.

`ROADMAP.md` describes the full contracted plan. `CURRENT_STATUS.md` is the authoritative day-to-day execution position. The detailed M2–M5 tasks below are a **planned implementation breakdown** for engineering and recovery. They may be refined before implementation as technical knowledge improves, provided milestone business scope remains consistent, approved commercial totals remain unchanged, and no out-of-scope functionality is silently introduced.

## 2. Recovery / New-Chat Instructions

If ChatGPT/Codex conversation history is unavailable, before changing code read:

1. `README.md`
2. `docs/PROJECT_CONTEXT.md`
3. `docs/ROADMAP.md`
4. `docs/REAL_WORKFLOW.md`
5. `docs/DATA_MODEL.md`
6. `docs/MILESTONE_1_SPEC.md` where relevant
7. `docs/AI_DOCUMENT_PIPELINE.md` where relevant
8. `docs/BUSINESS_RULES.md`
9. `docs/DECISIONS.md`
10. `docs/CURRENT_STATUS.md`
11. Recent Git history
12. Current Git status and diff

Trust committed repository state over remembered chat. Identify the latest completed and pushed task, audit all uncommitted work before changing anything, and never reset or discard interrupted work without that audit. Continue only the task marked **NEXT**, and never begin a later task without explicit approval.

GitHub and the repository documentation are the permanent project memory.

## 3. Approved Commercial Baseline

| Milestone | Hours | Price |
| --- | ---: | ---: |
| Milestone 1 — Core Intake & Drawing Review | 70 | $1,750 |
| Milestone 2 — Scope Builder & Trade Finder | 40 | $1,000 |
| Milestone 3 — Bid Invitations & Qualification | 40 | $1,000 |
| Milestone 4 — Proposal Generator & Award Workflow | 30 | $750 |
| Milestone 5 — Project Management Sync | 20 | $500 |
| **TOTAL** | **200 hours** | **$5,000** |

These hours, prices, milestone commercial totals, and total contract amount are approved and must not be altered casually.

## 4. Delivery Principles

- AI assists; humans retain approval authority.
- Financial arithmetic is deterministic.
- Immutable source, document, and revision history is preserved.
- Provenance matters, and human review is explicit.
- Workflow transitions are controlled.
- PostgreSQL is authoritative for durable workflow state.
- Redis and Celery are execution and transport infrastructure, not the source of truth.
- Organization and project isolation is enforced by the backend.
- Version history is preserved rather than overwritten.
- External or paid AI operations require explicit user intent.
- Existing BB Builders historical workflow evidence guides implementation.
- Contract scope remains disciplined; functionality outside an approved milestone requires explicit scope/change-order consideration.

The high-level workflow is:

```text
Draft
→ Documents Uploaded
→ AI Analysis
→ Human Scope Review
→ Trade Packages Ready
→ Contractor Discovery
→ Outreach Active
→ Bid Collection
→ Bid Leveling
→ Human Award Review
→ Final Proposal
→ Awarded Project
```

## 5. Milestone Dependency Flow

```text
M1 — trusted approved project intelligence
  feeds
M2 — scopes, trades, and contractor shortlist
  feeds
M3 — outreach, quotes, and bid comparison
  feeds
M4 — proposal and award
  feeds
M5 — awarded-project sync
```

Downstream milestones must not create a competing source of truth for approved upstream data.

## 6. Milestone 1 — Core Intake & Drawing Review

**70 hours / $1,750**

**Business objective:** Create the production foundation for project intake, immutable tender documents, deterministic PDF/page intelligence, structured AI assistance, provenance, human review, approved intelligence, and validation against real BB Builders historical tender data.

| Task | Status |
| --- | --- |
| M1-01 Backend & Local Development Foundation | COMPLETE |
| M1-02 Organization, Users, Authentication & Permissions | COMPLETE |
| M1-03 Project Production Data Model & API | COMPLETE |
| M1-04 Connect Projects UI to Backend | COMPLETE |
| M1-05 File / Document Storage Model | COMPLETE |
| M1-06 Production Upload Workflow | COMPLETE |
| M1-07 Document Processing Pipeline | COMPLETE |
| M1-08 PDF Page / Sheet Indexing | COMPLETE |
| M1-09 Structured AI Analysis | COMPLETE |
| M1-10 Provenance, Findings & Human Review | COMPLETE |
| M1-11 Intelligence Snapshot, Approval & Audit | COMPLETE |
| M1-12 Real BB Builders Project Validation & Milestone Polish | COMPLETE |

### M1-11 Intelligence Snapshot, Approval & Audit

- Create immutable `ProjectIntelligenceSnapshot` records.
- Assemble reviewed intelligence into an explicit version.
- Require human approval/sign-off and preserve its audit trail.
- Do not generate trade packages yet.

### M1-12 Real BB Builders Project Validation & Milestone Polish

- Validate end to end with real BB Builders historical project and tender evidence.
- Polish usability and error states.
- Complete milestone documentation and acceptance.
- Prevent Milestone 2 leakage.

## 7. Milestone 2 — Scope Builder & Trade Finder

**40 hours / $1,000**

**Business objective:** Turn approved project intelligence into reviewable construction scope and trade packages, then identify appropriate subcontractors while prioritizing BB Builders' existing network.

The following is a **planned implementation breakdown**:

### M2-01 Approved Intelligence → Scope Domain Model

Consume approved M1 intelligence, establish project scope entities, preserve source-intelligence linkage, and never regenerate approved facts with AI.

### M2-02 Trade Taxonomy & Trade Package Model

Create a controlled construction trade taxonomy, trade packages, inclusions/exclusions, and package status/versioning.

### M2-03 Deterministic Scope / Trade Package Generation

Generate draft packages from approved intelligence using deterministic business rules where possible. AI may assist wording or classification but may not silently redefine approved intelligence.

### M2-04 Human Scope & Trade Package Editing

Support estimator review and editing, preserve revisions/history, and provide an explicit readiness/approval checkpoint.

### M2-05 Subcontractor Company & Contact Data Model

Model Company and Contact as separate entities.

### M2-06 Trade Capabilities & Project Trade Relationships

Keep `Company`, `Contact`, `TradeCapability`, and `ProjectTradeRelationship` separately modeled. Do not collapse them into one subcontractor record.

### M2-07 Existing BB Builders Subcontractor Import / Search

Import/search the existing BB Builders network before external discovery where appropriate, preserving source and deduplication information.

### M2-08 Contractor Discovery & Deduplication

Support external discovery where needed, company/contact deduplication, and discovery-source recording.

### M2-09 Trade Package Contractor Shortlisting

Associate suitable contractors to project trade packages for human shortlist/review. Do not perform outreach.

### M2-10 Real Project Validation & Milestone Polish

Validate scopes, trades, and subcontractor matching against real BB Builders projects. Complete milestone acceptance without M3 outreach leakage.

**Acceptance boundary:** Approved intelligence → scope packages → trade packages → contractor discovery/shortlist.

**Not in M2:** Invitation sending, quote collection, bid leveling, proposals, award, or PM sync.

## 8. Milestone 3 — Bid Invitations & Qualification

**40 hours / $1,000**

**Business objective:** Allow BB Builders to invite selected subcontractors, track outreach and qualification, collect quote revisions, and compare bids on a structured, scope-aware basis.

The following is a **planned implementation breakdown**:

### M3-01 Invitation / Outreach Domain Model

Model invitation campaigns/batches, recipient status, and traceable immutable message history.

### M3-02 RFQ Template & Trade Package Invitation Builder

Use the BB Builders RFQ template with project/trade-package context, scope clarifications, and controlled generated content.

### M3-03 Recipient Selection & Invitation Batches

Select contractors from trade-package shortlists, group recipients, and prevent accidental duplicates.

### M3-04 Outreach Delivery Adapter & Retry/Audit

Provide delivery integration, retry/error handling, and message audit/history without silent duplicate sends.

### M3-05 Contractor Response / Qualification Tracking

Track invited, viewed, responded, declined, qualified, and related human qualification notes.

### M3-06 Bid / Quote Intake & Attachment Storage

Store immutable quote attachments with exact contractor and trade-package associations.

### M3-07 Bid Revision & Option / Alternate Modeling

Model quote revisions, alternates, options, permits, allowances, exclusions, and scope differences. Never reduce every quote to one price field.

### M3-08 Bid Leveling & Scope Comparison

Normalize comparisons without changing source quotes; compare inclusions, exclusions, alternates, options, and missing scope/conditions. Lowest price must not automatically mean recommended winner.

### M3-09 Human Bid Comparison / Shortlisting Workflow

Support estimator comparison, human qualification/shortlisting, and preserved selection reasoning.

### M3-10 Real Project Validation & Milestone Polish

Validate with actual BB Builders subtrade quotes and workflow evidence. Complete acceptance without proposal/award leakage.

**Acceptance flow:** Trade Packages → Contractors → Outreach → Responses → Quote Intake → Bid Leveling → Human Comparison.

**Not in M3:** Client proposal generation, award workflow, or PM sync.

## 9. Milestone 4 — Proposal Generator & Award Workflow

**30 hours / $750**

**Business objective:** Turn reviewed and selected trade bids and project intelligence into deterministic estimate/proposal versions, client-ready output, and a controlled award workflow.

The following is a **planned implementation breakdown**:

### M4-01 Estimate / Proposal Domain Model

Create estimate/proposal entities, immutable versions, project/customer relationships, status, and history.

### M4-02 Deterministic Financial Calculation Engine

Financial arithmetic must be deterministic; language models are not the calculator of record. Handle subtotal, markups, allowances, alternates, taxes and other explicitly defined calculations with deterministic rounding.

### M4-03 Selected Bid → Estimate Assembly

Use human-selected and qualified bids to assemble estimate package/line structure while preserving source-bid references.

### M4-04 Allowances, Alternates & Exclusions

Represent commercial conditions explicitly rather than burying them in prose, including proposal options where applicable.

### M4-05 Proposal Versioning & Immutable Revisions

Preserve estimate and proposal revisions and client PO/award evidence. Never overwrite prior client proposal versions.

### M4-06 Client Proposal PDF Generation

Produce versioned, dated, client-ready proposals with deterministic numbers and controlled wording.

### M4-07 Human Proposal Review / Finalization

Require explicit estimator approval; never finalize for the client automatically.

### M4-08 Award Decision & Subcontractor Award Records

Record selected subcontractors and human award decisions while preserving non-winning bid history.

### M4-09 Awarded Project Handoff State

Transition to Awarded Project and define the handoff payload for M5.

### M4-10 Real Project Validation & Milestone Polish

Validate against real BB Builders proposals, estimate revisions, and client award evidence; complete milestone acceptance.

**M4 is not:** Accounting software, a full ERP, an invoicing/change-order platform, or a full project-management system.

## 10. Milestone 5 — Project Management Sync

**20 hours / $500**

**Business objective:** Provide a narrow, reliable sync/handoff of awarded-project data into the selected project-management destination.

M5 is intentionally narrow. It does not turn this application into a complete construction-management platform.

The following is a **planned implementation breakdown**:

### M5-01 Awarded Project Handoff Data Contract

Define exactly which approved awarded-project data is eligible to sync.

### M5-02 PM Sync Target / Adapter Foundation

Isolate external PM integration behind a provider/target adapter and avoid coupling the domain to one external API.

### M5-03 Project Facts & Contact Sync

Sync project identity, address/site, client, contacts, and relevant dates.

### M5-04 Awarded Trade / Subcontractor Sync

Sync awarded trades, selected subcontractors, and key award metadata.

### M5-05 Schedule / Milestone Sync

Keep schedule sync narrow. Historical activity-level schedules inform architecture, but this contract covers only the approved milestone/schedule subset—not a scheduling engine.

### M5-06 Sync Mapping & External IDs

Maintain deterministic internal-to-external mapping and IDs to prevent duplicate external records.

### M5-07 Retry, Failure Recovery & Idempotency

Persist sync status, make retries safe, and prevent duplicate external entities.

### M5-08 Sync Audit / Status UI

Show synced, pending, and failed states with human-readable failures and sync history.

### M5-09 Real Awarded Project Validation

Validate using a representative awarded project.

### M5-10 Final Production Polish & Handover

Complete operational documentation, acceptance, and contracted-system handover.

## 11. Contract-Wide Out-of-Scope / Change-Control Boundary

Unless explicitly added through an approved change order or new scope, the current **$5,000 contract** does not automatically include full implementation of:

- Invoicing or accounts receivable/payable
- Accounting integrations
- Change-order or RFI management
- Full submittal or closeout-management workflows
- A complete construction scheduling engine
- Time tracking or payroll
- Equipment or safety-management platforms
- Field daily logs
- Full document control beyond the contracted bid workflow
- Full CRM replacement or complete ERP
- Advanced analytics/data warehouse
- Native mobile applications
- Unrelated post-award construction-management features

Historical schedules, submittals, closeout documents, and similar evidence may guide data architecture, but their existence does not expand contracted scope.

New requested functionality must be evaluated for whether it is already within milestone scope, replaces an equivalent planned feature, or requires a scope change/change order.

## 12. Current Approved Checkpoint

- Latest completed and pushed task: **M1-11 — Intelligence Snapshot, Approval & Audit**
- Latest pushed commit before M1-12: `18d29a4a4e50455133fefc6886b5acc76785d4a1`
- Latest completed local task: **M1-12 — Real BB Builders Project Validation & Milestone Polish**
- Next task: **M2-01 — Approved Intelligence → Scope Domain Model**
- Status: **MILESTONE 1 COMPLETE; M2 NEXT / NOT STARTED**

Update this checkpoint when the roadmap materially requires it. `CURRENT_STATUS.md` remains authoritative for day-to-day execution position.

## 13. Task Execution Rules

For every implementation task:

1. Read permanent documentation.
2. Confirm current HEAD and status.
3. Implement only the active task.
4. Add or update tests.
5. Run automated validation.
6. Perform manual validation.
7. Review the complete diff.
8. Update `CURRENT_STATUS.md`.
9. Commit one coherent task.
10. Review the commit.
11. Push only after approval.
12. Begin the next task only after explicit approval.

Interrupted Codex work must be audited before continuation; never blindly rerun or reset it. Never reset a local database containing relevant validation data unless explicitly approved. Never expose secrets, and keep `backend/.env` untracked. Use `127.0.0.1` consistently for local frontend/backend development.

Windows Celery development command, run from `backend`:

```powershell
.venv\Scripts\celery.exe -A config worker --loglevel=INFO --pool=solo
```

## 14. Roadmap Maintenance Rules

- Commercial milestone totals may not be changed casually.
- Planned task decomposition may be refined before its milestone begins.
- Document architectural or material refinements in `DECISIONS.md`.
- Do not silently remove task intent or add out-of-scope work.
- Mark tasks as planned until implementation begins.
- `CURRENT_STATUS.md` must not claim completion before required validation, commit, and push.
