# Real BB Builders Workflow

## Evidence boundary

This document distinguishes three categories:

1. **Observed real workflow:** behavior supported by review of the historical JD Sports / Intercity Thunder Bay project artifacts.
2. **Planned product workflow:** intended system behavior based on those observations and approved product direction.
3. **Future opportunity:** useful functionality that is not committed to Milestone 1.

The historical sample is valuable but is not proof that every BB Builders project follows exactly the same process. Unknowns must be validated with users rather than converted into silent product assumptions.

## Observed real workflow

### 1. Opportunity and tender receipt

A real opportunity arrives as a mixed tender package, not as a single clean PDF. The historical material included or demonstrated the need to accommodate:

- architectural, mechanical, electrical, and structural drawings;
- client scope documents;
- landlord requirements;
- bid requirements and forms;
- responsibility schedules;
- vendor or specialty drawings;
- spreadsheets and Word documents;
- specifications and addenda.

The package must therefore be understood as a related document set whose files can disagree, supplement one another, or be revised over time.

### 2. Project intake and package organization

Estimators establish project facts, deadlines, contacts, location, client requirements, and the document set. Information may be repeated inconsistently across files. Important dates and bid conditions cannot safely be inferred from one drawing sheet alone.

### 3. Cross-document review

Review combines drawings, scope narratives, responsibility schedules, landlord material, bid forms, specifications, and addenda. The relevant output is structured project intelligence, including:

- project facts and key dates;
- document and sheet index;
- drawing disciplines;
- required trades;
- scope findings;
- responsibility assignments;
- owner-supplied and third-party items;
- permits and inspections;
- landlord requirements;
- bid conditions;
- exclusions and clarification flags;
- submittal and closeout requirements when discovered.

### 4. Responsibility interpretation

Required work does not necessarily mean a BB Builders subcontractor supplies and installs everything. Supply, installation, coordination, and third-party responsibility may be split.

Example:

| Scope item | Responsibility |
|---|---|
| Security grille supply | Owner / JD Sports |
| Security grille installation | Specialty vendor |
| Supporting work and coordination | General contractor |
| Evidence | Responsibility schedule |

This separation is central to accurate scope preparation and later bid leveling.

### 5. Human interpretation and clarification

Documents can contain ambiguity or conflict. Estimators determine whether information is accepted, rejected, edited, or requires clarification. A reliable system must show the evidence and preserve the human decision.

### 6. Trade procurement and quotation review

Historical trade lists indicate that a company or contact may support several trades. Company identity, people, capabilities, and project-specific trade relationships are distinct concepts.

Historical quotes demonstrate that comparison requires more than base price. Relevant dimensions include revisions, alternates, allowances, exclusions, taxes, owner-supplied items, permits, material choices, scope differences, schedule assumptions, and selected options. Lowest submitted price is not automatically the best bid.

### 7. GC proposal and revisions

Historical proposals preserve commercial revisions. The expected pattern is Proposal → Version 1 → Revision 1 → Revision 2, rather than overwriting a single record.

### 8. Award and downstream handoff

After client approval, the project may proceed into subcontractor awards, purchase orders, compliance, schedule, and project handoff. Historical submittals also show revision-and-review cycles, while historical Smartsheet schedules show that one trade may correspond to many construction activities.

These observations inform the future model but are outside Milestone 1 implementation.

## Planned product workflow

### End-to-end lifecycle

```text
RFP / Bid Opportunity
  → Go / No-Go Decision
  → Persistent Project Intake
  → Mixed Tender Package Upload
  → Validation and Immutable Storage
  → Document Classification and Indexing
  → AI-Assisted Structured Analysis
  → Conflict and Confidence Review
  → Human Finding Review
  → Project Intelligence Approval
  → Human Scope Review
  → Trade Packages / RFQs
  → Contractor Discovery and Controlled Outreach
  → Bid Intake and Qualification
  → Bid Leveling and Human Trade Selection
  → GC Proposal and Revisions
  → Client Approval
  → Awarded Project
  → Subcontract Awards / POs / Compliance
  → Schedule and Project Handoff
```

Milestone 1 ends after persistent human approval of structured project intelligence. The subsequent nodes define integration boundaries, not current delivery scope.

### Milestone 1 operating flow

1. An authenticated organization member creates a project and records project metadata and timezone.
2. The user uploads one or more tender files.
3. The system validates and stores original binaries immutably.
4. The system creates logical documents and immutable revisions rather than overwriting files.
5. Background jobs classify and process supported formats.
6. PDF drawings are indexed by page and sheet where detectable.
7. Task-specific analysis produces structured findings and provenance.
8. Cross-document consolidation identifies duplicates, dependencies, and conflicts.
9. Users inspect findings by category and navigate to supporting sources.
10. Users accept, edit and accept, reject, or request clarification for each finding.
11. Material conflicts remain unresolved until a human decision is recorded.
12. The system freezes the effective findings, reviews, and resolved material conflicts into an immutable project intelligence snapshot.
13. An authorized user gives final approval to that exact snapshot.
14. The system preserves analysis inputs, task runs, outputs, conflicts, reviews, snapshots, approvals, and audit history.
15. A new material document revision creates a new analysis context and may require re-review; it never silently mutates the prior approved record.

## Planned information domains

Project intelligence should be structured into stable categories rather than returned as one narrative:

- project facts;
- documents, pages, and drawing sheets;
- drawing disciplines;
- required trades;
- scope observations;
- responsibility assignments;
- owner-supplied items;
- third-party scope;
- permits and inspections;
- landlord requirements;
- schedule and key dates;
- bid conditions;
- exclusions and clarification flags;
- submittal requirements;
- closeout requirements;
- provenance, confidence, conflict, and human review state.

## Future opportunities, not Milestone 1

- Trade-scope authoring and approval
- Trade packages and RFQ generation
- Contractor discovery and capability matching
- Controlled outbound email and follow-up
- Inbound quote ingestion and quote revision tracking
- Deterministic bid normalization and leveling
- Human trade selection
- Versioned GC proposals and client acceptance
- Subcontract awards and purchase orders
- Compliance document tracking
- Detailed schedule tasks distinct from trades
- Versioned submittals and review outcomes
- Change orders, invoices/progress claims, and closeout
- Smartsheet and other integrations

See [MILESTONE_1_SPEC.md](./MILESTONE_1_SPEC.md) for the binding current scope and [DATA_MODEL.md](./DATA_MODEL.md) for present and future conceptual entities.
