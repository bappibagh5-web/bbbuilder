# Core Business Rules

These rules are implementation invariants. Where a rule requires a technical choice that has not been finalized, the invariant remains binding while the mechanism is recorded as unresolved in [DECISIONS.md](./DECISIONS.md).

## M4 estimate and proposal foundation

1. Estimate and Proposal are separate stable project aggregates; their versions are append-only.
2. A ProposalVersion permanently references one exact EstimateVersion and never follows a later estimate dynamically.
3. Estimate and Proposal creation is an explicit Admin/Estimator action. M3 Selected for Proposal never creates M4 records automatically, and Viewer remains read-only.
4. Subcontractor bid/comparison amounts remain procurement evidence until an Admin/Estimator explicitly assembles a finalized Selected-for-Proposal review into one exact Draft EstimateVersion.
5. The contractor Base Bid and BB Builders M3 leveling adjustments remain separate immutable EstimateLines with exact review, comparison-entry, BidRevision, ScopePackageVersion, company, and adjustment provenance.
6. Estimate arithmetic uses backend Decimal only. Order is Base Bid, signed M3 leveling, included allowances, explicitly included ADD/DEDUCT alternates, sequenced explicit non-tax adjustments, pre-tax subtotal, then explicit tax. Each calculated adjustment rounds `ROUND_HALF_UP` to 0.01.
7. Missing financial values are null, never zero. Mixed currencies block totals; no FX, markup, overhead, profit, contingency, tax rate, allowance amount, or alternate inclusion may be inferred.
8. Exclusions are explicit non-arithmetic statements. Contractor commercial terms are never promoted into estimate treatment without a separate human action.
9. Historical EstimateVersions do not follow later M3 records or later Estimate versions. ProposalVersion continues to bind one exact EstimateVersion.
10. Proposal finalization is explicit and atomically freezes both the ProposalVersion and its exact EstimateVersion; later correction requires successor versions.
11. Finalized proposals preserve structured client/project/financial snapshots and deterministic fingerprints so mutable upstream metadata cannot change history.
12. Client proposal previews/PDFs never expose contractor Base Bid, M3 leveling, internal rates, procurement rationale or internal source identifiers.
13. Final PDFs are private append-only, artifact-versioned and template-versioned immutable FileAssets generated locally without an external provider. Corrected rendering creates a new artifact and never overwrites historical files; repeated generation for the same template is idempotent.
14. Proposal finalization is not acceptance or award; awards, subcontracts and purchase orders remain later human-controlled work.

## Organization and access

1. All production business records belong to an organization, initially BB Builders Ltd.
2. Users act through organization membership and a role: Admin, Estimator / Operator, or Viewer.
3. Authorization is enforced by Django, not only by hidden frontend controls.
4. External client and vendor accounts are future scope.
5. Sensitive authentication credentials or bearer tokens must not be stored in `localStorage`.

## Project and time

1. Every project has an explicit timezone.
2. Audit timestamps are stored in UTC.
3. Project deadlines and schedule dates are interpreted and displayed in the project timezone.
4. Date-only obligations must remain date-only; they must not acquire an arbitrary UTC time that changes the displayed day.
5. Material changes to project metadata must be auditable.

## Files and revisions

1. Original uploaded file bytes are immutable.
2. A replacement drawing, specification, addendum, or other source creates a new `DocumentRevision`; it does not overwrite the prior revision.
3. File identity should include an integrity checksum in addition to filename and size.
4. The system must preserve the relationship among a logical document, its revisions, and the file assets behind them.
5. A revision may supersede another only through an explicit relationship or review action.
6. Derived artifacts may be regenerated where practical, but their retention and reproducibility policy must be documented.
7. Unsupported formats may be retained as source material without being intelligently parsed.
8. Milestone 1 intelligent formats are PDF, DOCX, XLSX, and JPG/PNG. PDF is the primary construction-drawing format. DWG/CAD parsing is not required.

## Analysis and provenance

1. AI output is structured, schema-validated data, not only prose.
2. Every material finding must be associated with the analysis run that produced it.
3. Important findings retain source document revision, page or sheet where possible, supporting reference/evidence, and confidence or risk information.
4. A finding may have multiple sources, and one source may support multiple findings.
5. The absence of precise page provenance must be explicit; it must not be fabricated.
6. Cross-document analysis must consider drawings, specifications, addenda, responsibility schedules, landlord requirements, and other package material together.
7. AI services are narrow and task-specific. No unrestricted agent may autonomously mutate approved project intelligence.
8. AI output is always treated as proposed information until human-reviewed under the approval rules below.

## Confidence and conflicts

1. Confidence is decision support only and never constitutes approval.
2. Low-confidence findings are prominently flagged for review.
3. Conflicting sources are represented explicitly and routed to human resolution.
4. The system must not silently choose one conflicting source.
5. Confidence presentation thresholds may affect prioritization, but may not bypass review.
6. Conflict resolution records the reviewer, decision, time, rationale where required, and the evidence considered.

## Human review and approval

1. Each finding has one of these review outcomes:
   - Accepted
   - Edited / Accepted
   - Rejected
   - Needs Clarification
2. Edited / Accepted preserves both the original extracted value and the accepted human-edited value.
3. Rejection does not delete the extracted record.
4. Needs Clarification remains unresolved and must be visible in approval readiness checks.
5. Material conflicts are first-class records connecting all participating findings and/or provenance sources; conflict resolutions are historical and auditable.
6. Final project-intelligence approval occurs only after required findings and conflicts have been reviewed according to the approval policy.
7. The effective reviewed findings, reviews, and resolved conflicts are frozen into an immutable `ProjectIntelligenceSnapshot` with a versioned manifest and hash.
8. Approval records identify the exact approved snapshot, approver, timestamp, and any permitted approval note. An `AnalysisRun` alone is not an approval target.
9. Approved findings must not be silently modified.
10. A material new document revision or analysis produces new findings or a new intelligence version, identifies superseded/conflicting information, and triggers re-review where applicable.
11. Only an approved intelligence snapshot may feed later scope, procurement, bid, or proposal workflows.
12. Revocation or replacement of approval must be explicit and auditable.
13. A project-intelligence snapshot is project-level and is assembled only from explicitly selected successful analysis runs belonging to that project. It includes each selected run's complete materialized finding set; individual findings cannot be cherry-picked.
14. At most one selected analysis run may target a given document revision, and that revision must be its document's explicit current revision when a new snapshot is created.
15. Admin and Estimator / Operator memberships may create and approve snapshots. Self-approval is permitted, but approval is always a separate explicit action. Viewers are read-only.
16. Snapshot approval leaves `Project.status` at `human_scope_review`. Milestone 2 owns trade-package creation and any transition to `trade_packages_ready`.

## Responsibility mapping

1. Scope responsibility is not represented by one undifferentiated “required trade” field.
2. A scope item may separately record:
   - supply responsibility;
   - installation responsibility;
   - general-contractor coordination or supporting-work responsibility;
   - owner, landlord, vendor, utility, consultant, or other third-party responsibility.
3. Owner-supplied does not imply owner-installed.
4. Third-party installation does not eliminate GC coordination obligations.
5. Responsibility conclusions must retain their source evidence and human review state.

## Versioning and history

1. Business history is appended or superseded explicitly, not silently overwritten.
2. Document revisions, analysis runs, findings, review decisions, and approvals remain attributable to their versions.
3. Future quote, proposal, submittal, and similar commercial records must preserve revision history.
4. “Current” is a derived or explicitly designated status; it does not mean older records are deleted.

## Financial and contractual control

1. Deterministic application code performs authoritative financial calculations.
2. AI may extract proposed financial inputs but is not the accounting engine.
3. AI cannot autonomously select the lowest bidder, accept a quote, issue a proposal, or approve a contractual condition.
4. Later bid leveling must account for quote revisions, alternates, allowances, exclusions, taxes, permits, material selections, owner-supplied items, schedule assumptions, and scope differences.
5. Lowest submitted price is not automatically the selected or best bid.

## Auditability

1. Security-sensitive and business-significant events create server-side audit records.
2. Audit events include actor, organization, action, target, UTC timestamp, and relevant before/after or contextual information.
3. Client-generated display activity is not a substitute for the production audit trail.
4. Audit records must not be editable through ordinary business workflows.
5. Automated actions identify the system or processing job responsible and remain traceable to the initiating user or event when applicable.

## System ownership

1. PostgreSQL is the system of record for business state and metadata.
2. S3-compatible storage is the system of record for file bytes; PostgreSQL stores controlled references and metadata.
3. Redis and Celery transport work but do not own authoritative business state.
4. OpenAI responses are inputs to persisted analysis records, not an independent store of approved truth.
5. n8n may coordinate later integrations but must not own authoritative project, document, review, or approval state.
## Human bid review

- Human bid review may start only from one exact BidComparison that is Ready for Human Review.
- Every frozen comparison entry starts Undecided; no price, adjustment, score, AI output or company state may shortlist or select it automatically.
- Bid-review Shortlisted/Not Shortlisted is separate from contractor-discovery shortlist and outreach approval.
- Selected for Proposal requires exactly one Shortlisted entry from the same comparison plus explicit human rationale. It is not an award or contractor notification.
- No Acceptable Bid is a valid outcome and requires a null selected entry plus explicit human rationale.
- Finalization requires every entry decided, a legal explicit outcome and rationale, then freezes decisions, selection, actor and time. Corrections preserve the finalized record through a successor review.
- Admin and Estimator may mutate Draft reviews; Viewer is read-only. Actual award belongs to later workflow.
