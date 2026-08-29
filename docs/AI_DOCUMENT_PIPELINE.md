# AI Construction-Document Pipeline

## Objective

Transform a mixed construction tender package into structured, source-traceable proposed project intelligence that a human can review and approve. The pipeline must preserve original material, versions, provenance, conflicts, and analysis configuration.

It is not an autonomous estimator. It proposes evidence-backed information and routes uncertainty to BB Builders personnel.

## Pipeline overview

```text
Upload
  → Validation
  → Immutable Storage
  → File Classification
  → Text / Metadata Extraction
  → Page / Sheet Indexing
  → Discipline Classification
  → Targeted Visual Analysis
  → Structured Extraction
  → Cross-Document Consolidation
  → Conflict Detection
  → Human Review
  → Project Intelligence Approval
```

Each stage writes durable state through Django/PostgreSQL. Celery executes expensive work. Redis transports jobs but is not authoritative. Original and derived bytes are kept in S3-compatible storage according to their retention policies. A complete `AnalysisRun` contains independently traceable `AnalysisTaskRun` records for its narrow services.

## 1. Upload

The backend creates an authorized upload intent and provisional `FileAsset` record. The browser uploads through the approved private-storage mechanism. The backend verifies completion before processing.

Capture:

- organization/project ownership;
- original filename;
- declared MIME type and size;
- uploader and UTC timestamp;
- generated object key;
- upload state and correlation identifier.

Do not use filenames as unique identity and do not expose permanent public object URLs.

## 2. Validation

Validate before normal processing:

- upload completeness;
- allowed size and format policy;
- detected MIME type versus declaration/extension;
- checksum and duplicate indicators;
- basic file readability;
- malware/quarantine result when the selected implementation requires it.

Failure states must be durable and actionable. A quarantined or invalid file cannot silently enter analysis. The exact limits and scanning mechanism remain unresolved.

## 3. Immutable storage and revision assignment

After verification, the original file becomes immutable. Create or associate a logical `Document`, then create an immutable `DocumentRevision` pointing to the file.

Revision assignment may begin with user-provided information and later receive detected suggestions. A newer file never replaces bytes behind an existing revision. Explicitly record supersession and addendum relationships. `Document.current_revision` is the sole authoritative current-revision reference. Changing it is a validated and audited backend transition; filename, date, label, or upload order never changes it implicitly.

## 4. File classification

Classify the source using deterministic metadata first and AI only where useful. Suggested categories include architectural drawings, engineering drawings, specifications, addendum, client scope, landlord requirement, responsibility schedule, bid requirements/form, schedule, spreadsheet, image/reference, and unknown.

Classification produces a proposed value with confidence and supporting signals. Users can correct the logical classification without changing the source file.

Mixed files may contain several logical sections. The implementation must decide whether to split them into logical child documents or retain one document with section indexing; this taxonomy remains subject to detailed design.

## 5. Text and metadata extraction

Use format-specific adapters. PDF construction-document intelligence has the highest Milestone 1 priority and receives full page/sheet indexing and targeted drawing analysis. Other supported formats receive appropriate extraction without requiring identical drawing-level depth:

- **PDF:** native text, metadata, page geometry, embedded image characteristics, and renderability.
- **DOCX:** paragraphs, headings, tables, headers/footers, and document metadata while retaining structural location.
- **XLSX:** workbook, sheet names, bounded cell ranges, tables, and formulas/values as permitted; preserve sheet/cell locators.
- **JPG/PNG:** image metadata and OCR/vision extraction where required.

Do not flatten all content into an untraceable text blob. Extracted units retain a locator to revision/page/sheet/section/cell range. OCR or parsing quality signals should be recorded.

## 6. Page and drawing-sheet indexing

For every PDF revision, create stable page records using zero- or one-based internal indexing consistently while separately preserving printed page labels.

For construction drawings, attempt to detect:

- sheet number;
- sheet title;
- discipline;
- revision notation/date where visible;
- orientation and page dimensions;
- title-block region and confidence.

Detection is proposed information and may be corrected. Page identity remains bound to the immutable document revision.

## 7. Discipline classification

Classify pages/sheets into controlled disciplines such as architectural, mechanical, electrical, structural, civil, fire protection, interiors, landscape, or general. Use filename/title-block/text signals before or alongside vision.

Discipline classification helps route targeted extraction; it must not by itself create an approved required-trade conclusion.

## 8. Targeted visual analysis

Use visual analysis only for pages where it adds value, rather than sending every page to an unrestricted model at maximum detail. Routing signals may include low native-text coverage, drawing classification, title-block detection, schedules, legends, notes, and relevance to missing categories.

Possible targeted tasks:

- title-block and sheet metadata extraction;
- general-note and key-note interpretation;
- responsibility or equipment schedule reading;
- visual confirmation of discipline and referenced scope;
- identification of source regions supporting a finding.

Record the exact page/render input, rendering version/resolution, model/task version, and result schema. Visual interpretations remain proposed findings.

## 9. Structured extraction

Run narrow, schema-validated services rather than one broad prompt. Recommended services include:

1. **Project facts extractor:** name, number, address, client, areas, contacts, and identifiers.
2. **Dates and bid conditions extractor:** deadlines, site visits, submission requirements, bonding or pricing conditions.
3. **Document/sheet indexer:** document identity, revision, sheet number/title, discipline.
4. **Required-trade detector:** proposed trades with evidence and rationale.
5. **Scope observation extractor:** discrete work observations rather than broad narrative summaries.
6. **Responsibility mapper:** supply, installation, GC coordination/support, owner, landlord, vendor, utility, and other third-party roles.
7. **Owner/third-party scope extractor:** separately classifies supplied, installed, coordinated, and excluded responsibilities.
8. **Permit and inspection extractor:** authority, responsibility, fee/allowance indication, and evidence.
9. **Landlord requirement extractor:** landlord criteria, approvals, rules, and dependencies.
10. **Submittal/closeout requirement detector:** records requirements when discovered without implementing later workflows.
11. **Risk and clarification detector:** ambiguity, missing inputs, exclusions, and questions requiring human action.

Every service execution creates an `AnalysisTaskRun` beneath the complete `AnalysisRun`. It records task type, status, source inputs, provider/model, prompt version, schema version, task-configuration version, timestamps, attempt/error details, and available usage/cost metadata. Tasks can succeed, fail, or retry independently. Findings point to the exact task run that produced them.

Every service returns stable category codes, a schema version, structured values, confidence/risk indicators, and source candidates. Invalid output is rejected, retried through controlled repair, or marked failed; it never bypasses validation.

## 10. Cross-document consolidation

Consolidation groups findings referring to the same subject while preserving every source. It may:

- combine compatible supporting evidence;
- identify exact or near duplicates;
- distinguish a general requirement from a more specific qualification;
- apply explicit document/revision precedence rules only where those rules are known;
- propose supersession links following new revisions;
- identify missing or incomplete category coverage.

The result is still a proposed intelligence set. Consolidation must not erase the raw run findings.

## 11. Conflict detection

A conflict exists when relevant sources make materially incompatible assertions, including differing dates, responsibilities, quantities, scope inclusions, revision instructions, or bid conditions. It is represented by a first-class `IntelligenceConflict`, not merely a flag on a finding.

Conflict detection should combine deterministic comparisons where possible with narrowly scoped semantic comparison where required. Store:

- findings and sources in conflict;
- conflict type and materiality;
- proposed explanation, if any;
- confidence in conflict detection;
- human resolution status, outcome, rationale, actor, and timestamp;
- superseded or previous resolution where a resolution changes.

The conflict connects multiple participating findings and/or provenance sources and preserves every competing claim. For example, a March 31 deadline in a drawing and April 2 in an addendum remain separate sourced findings; the conflict record connects them, and a human resolution determines the effective reviewed value. Resolution is historical and auditable.

Addenda or newer revisions may have known precedence, but the system must not assume that every newer document resolves every conflict. A human sees and resolves material conflicts.

## 12. Human review

The UI presents findings by category with source links, original structured values, confidence, conflict state, and analysis-run context. Review outcomes are:

- Accepted
- Edited / Accepted
- Rejected
- Needs Clarification

An accepted edit preserves the original extraction and stores a validated human value. Reviews are attributed and historical. Source navigation should open the exact revision/page/sheet when available.

## 13. Project intelligence approval

Deterministic backend logic evaluates readiness against the approved policy. Once findings are reviewed and material conflicts are resolved, the backend creates an immutable `ProjectIntelligenceSnapshot`. Its versioned manifest and hash capture the source analysis run, included finding IDs, effective finding-review IDs, and relevant resolved intelligence-conflict IDs.

`ProjectIntelligenceApproval` references exactly that snapshot. An `AnalysisRun` alone cannot be approved because it does not identify the later human reviews and resolutions. Approval does not alter extracted findings. It authorizes a specific reviewed snapshot for downstream consumption. A new material revision or analysis creates a new candidate snapshot, compares it with the approved baseline, and requires re-review where affected.

## Provenance lifecycle

Provenance begins before the AI call and must survive every transformation:

```text
FileAsset object key + checksum
  → DocumentRevision
  → Page/Sheet or structured document locator
  → Extracted text/image region
  → Task-specific model input reference
  → AnalysisTaskRun
  → Raw structured finding
  → FindingSource relation
  → Consolidated finding
  → Human review
  → Resolved IntelligenceConflict records
  → Immutable ProjectIntelligenceSnapshot manifest/hash
  → ProjectIntelligenceApproval
```

At any approved finding, an authorized user or audit process should be able to answer:

- Which original file and immutable revision supported this?
- Which page, drawing sheet, section, sheet/cell range, or image region was used?
- What bounded evidence was presented?
- Which analysis run, pipeline, schema, and model produced the proposal?
- Which narrow analysis task run, prompt/configuration version, and attempt produced it?
- Were other sources supportive, qualifying, or contradictory?
- What did the human reviewer decide, and was the value edited?
- Which approval made this information eligible for downstream use?

If the pipeline cannot provide a precise locator, it records a revision-level source and an explicit reason rather than inventing precision.

## Processing states and recovery

Use controlled machine-readable states, with user-facing labels mapped separately. A possible lifecycle is:

```text
pending_upload → uploaded → validating → quarantined/invalid/validated
validated → queued → processing → needs_review/completed/failed
```

The final state vocabulary should be designed once across file, revision, processing-job, and analysis-run aggregates rather than sharing one ambiguous status field.

Jobs should have:

- idempotency keys and input fingerprints;
- bounded retries by error class;
- explicit terminal failure;
- heartbeat/timeout handling;
- correlation IDs;
- safe cleanup of temporary worker material;
- reproducible configuration metadata;
- durable progress or stage state when meaningful.

A processing job must target only an allowed Milestone 1 entity: `FileAsset`, `DocumentRevision`, `DocumentPage`, `AnalysisRun`, or `AnalysisTaskRun`. Avoid an unconstrained polymorphic `GenericForeignKey`; use explicit strongly validated relationships or another design that preserves database referential integrity and enforces the appropriate target for each job type.

## Security and privacy

- Keep source storage private.
- Authorize every download and source preview.
- Avoid embedding permanent credentials in URLs or logs.
- Use temporary worker storage with controlled cleanup.
- Send only required pages/content to AI services for a task.
- Record provider/model and applicable data-handling configuration.
- Redact secrets and unnecessary personal information from logs.
- Do not process quarantined files.

## Evaluation strategy

Before selecting models or thresholds, create a representative, access-controlled evaluation set from approved/sanitized BB Builders documents. Evaluate per task rather than using one aggregate “AI accuracy” score. The key milestone demonstration uses one representative real or sanitized BB Builders tender package through the complete end-to-end workflow.

Measure at least:

- project-fact exactness;
- date/deadline accuracy;
- sheet-index accuracy;
- required-trade precision and recall;
- responsibility-role accuracy;
- provenance correctness;
- conflict detection usefulness;
- schema validity and retry rate;
- human edit/rejection rate;
- latency and cost by package/page/task.

Confidence should be calibrated against observed outcomes where possible. Model changes require regression evaluation on the task-specific set.

## Pipeline boundaries

Milestone 1 ends at approved project intelligence. The pipeline does not autonomously generate RFQs, contact subcontractors, select bids, prepare a binding proposal, or perform financial calculations. Later services may consume only explicitly approved intelligence through controlled interfaces.
