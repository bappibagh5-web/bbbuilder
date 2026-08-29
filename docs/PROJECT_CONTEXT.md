# BB Builders AI Bid Automation System — Project Context

## Purpose of this document

This document is the durable starting point for engineers and future implementation sessions. It records the business context, approved product direction, current repository state, architectural boundaries, and the scope of the current milestone. Detailed workflow, data, pipeline, rules, and decisions are maintained in the companion documents in this directory.

## Client and business context

The client is **BB Builders Ltd.** The product is an AI-assisted operating system for construction preconstruction and subcontractor bidding.

The system is intended to reduce repetitive bid administration and help estimators interpret tender packages, structure project intelligence, prepare trade scopes, procure subcontractor coverage, compare quotations, and assemble general-contractor proposals. It is not intended to replace estimators or make unsupervised contractual or financial decisions.

## Product objectives

The intended product should:

- preserve original tender documents and their revisions;
- extract structured, traceable project intelligence from mixed document packages;
- identify required trades, responsibilities, risks, conditions, and missing information;
- direct uncertain or conflicting findings to human review;
- preserve human control at financially and contractually important stages;
- create an auditable history of documents, analysis, edits, approvals, bids, and proposals;
- reduce manual coordination without making AI the system of record.

## Terminology

- **Bid opportunity:** A potential project before BB Builders decides whether to pursue it.
- **Project:** An organization-owned bid or awarded job with metadata, participants, documents, and workflow state.
- **Bid package / tender package:** The complete set of drawings, specifications, addenda, schedules, forms, and supporting material received for bidding.
- **File asset:** A stored binary object and its technical metadata.
- **Document:** The logical business document, such as an architectural drawing set or addendum.
- **Document revision:** An immutable version of a document associated with a specific file asset.
- **Drawing sheet / document page:** An indexed unit within a revision used for navigation and provenance.
- **Analysis run:** One versioned execution of the document-intelligence pipeline against an explicit input set.
- **Finding:** A structured fact, obligation, trade requirement, risk, responsibility, condition, or other extracted item.
- **Provenance:** The source document revision, page or sheet, reference, evidence, and analysis run supporting a finding.
- **Review state:** The human disposition of a finding: Accepted, Edited / Accepted, Rejected, or Needs Clarification.
- **Project intelligence approval:** Final human approval of a reviewed intelligence set for controlled downstream use.
- **Trade:** A construction discipline or subcontracted work category.
- **Scope item:** A discrete work requirement that may have separate supply, installation, coordination, and third-party responsibilities.
- **System of record:** The authoritative persistent store. PostgreSQL will serve this role.

## Intended product lifecycle

The longer-term lifecycle is:

1. Bid Opportunity
2. Project Intake
3. Bid Documents
4. AI Document Review
5. Human Scope Review
6. Trade Packages / RFQs
7. Contractor Discovery
8. Controlled Outreach
9. Bid Intake
10. Bid Qualification / Leveling
11. Human Trade Selection
12. GC Proposal
13. Proposal Revisions
14. Client Approval
15. Awarded Project
16. Subcontractor Awards / Purchase Orders
17. Compliance
18. Schedule / Project Handoff

Later project-management opportunities may include submittals, schedules, change orders, invoices or progress claims, and closeout documents. These are future domains, not implied Milestone 1 deliverables.

See [REAL_WORKFLOW.md](./REAL_WORKFLOW.md) for the distinction between observed historical practice and planned product behavior.

## Current repository state

The repository contains the approved frontend demonstration built with Next.js, TypeScript, React, and Tailwind CSS. It models the wider lifecycle using centralized deterministic fixtures and temporary React state.

The current demo has:

- an approved visual and interaction reference;
- project, document, AI-review, scope, procurement, bid, proposal, and award screens;
- simulated file selection and processing;
- simulated AI findings with confidence and source references;
- simulated review, approval, revision, and handoff interactions;
- no backend, database, authentication, durable upload, API, OpenAI connection, or persistence.

The existing frontend should remain the UX baseline wherever practical. Production work should replace fixtures and simulations behind the existing interaction patterns rather than redesigning the product without a separate decision.

## Approved production architecture

- **Frontend:** Existing Next.js + TypeScript application
- **UI:** Existing Tailwind and component system
- **Backend:** Django and Django REST Framework
- **System of record:** PostgreSQL
- **File storage:** S3-compatible abstraction, likely DigitalOcean Spaces in production
- **Background processing:** Celery with Redis
- **AI:** OpenAI API using structured, schema-validated output and narrow task-specific services
- **Document processing:** Python with PyMuPDF, PDFium, or suitable equivalents
- **Integrations:** n8n may later provide integration glue, but it must not become the system of record

Core business rules, approvals, permissions, workflow transitions, and persistent state belong in Django/PostgreSQL. Browser state must not be authoritative for production decisions.

## Human-control philosophy

AI interprets and extracts; it does not independently approve contractual facts or calculate authoritative financial results. Important findings must remain traceable to sources. Confidence assists prioritization but never substitutes for review. Conflicting or low-confidence findings must be visible to a human.

Human-reviewed information must not be silently overwritten. A new document revision or analysis produces new records, identifies affected or superseded information, and triggers re-review when material. Reviewed findings and resolved conflicts are frozen into an immutable project intelligence snapshot, and approval references that exact snapshot. Only an explicitly approved snapshot may feed later bidding workflows.

## Current milestone

**Milestone 1: Production Foundation, Project Intake & AI Drawing/Document Review**

The target outcome is that an authorized BB Builders user can create a persistent project, upload and preserve a real bid package, monitor processing, receive structured and sourced project intelligence, review findings, resolve material conflicts, approve an immutable intelligence snapshot, and retain an auditable record across logout and reload.

The detailed implementation specification is in [MILESTONE_1_SPEC.md](./MILESTONE_1_SPEC.md). The conceptual model is in [DATA_MODEL.md](./DATA_MODEL.md), and the processing design is in [AI_DOCUMENT_PIPELINE.md](./AI_DOCUMENT_PIPELINE.md).

## Milestone boundary

Milestone 1 does not include live contractor discovery, outbound RFQ campaigns, inbound email bid ingestion, real bid leveling, proposal generation, subcontractor awards, purchase orders, Smartsheet integration, change orders, invoicing, submittals, schedules, or closeout management.

The data architecture may reserve clean extension points for these domains. It must not implement them prematurely or present them as Milestone 1 acceptance criteria.

## Document authority and maintenance

- [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md) provides orientation and scope.
- [REAL_WORKFLOW.md](./REAL_WORKFLOW.md) records observed and planned workflow.
- [DATA_MODEL.md](./DATA_MODEL.md) defines conceptual entities and ownership.
- [MILESTONE_1_SPEC.md](./MILESTONE_1_SPEC.md) defines the current delivery contract.
- [AI_DOCUMENT_PIPELINE.md](./AI_DOCUMENT_PIPELINE.md) defines processing stages and provenance.
- [BUSINESS_RULES.md](./BUSINESS_RULES.md) records invariant business behavior.
- [DECISIONS.md](./DECISIONS.md) records decided and unresolved architecture choices.

If implementation requires a change to an approved decision, record the decision and consequences in `DECISIONS.md` before or alongside the implementation change.
