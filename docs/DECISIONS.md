# Architecture and Decision Log

## How to use this log

This file records decisions that constrain implementation and explicitly identifies unresolved choices. A decided item should be changed only through a new dated decision entry describing the reason and consequences. Do not silently treat an unresolved item as approved.

Statuses:

- **Decided:** Approved direction.
- **Provisional:** Working direction requiring validation before it becomes a durable production constraint.
- **Unresolved:** A decision is required before the affected implementation is finalized.

## Decided items

### D-001 — Preserve the approved frontend as the UX baseline

**Status:** Decided
**Decision:** Continue with the existing Next.js and TypeScript frontend and preserve its approved UX wherever practical. Production work replaces fixtures and simulations without unnecessary redesign.
**Consequence:** API integration should be introduced behind stable views. Material UX changes require a separate decision.

### D-002 — Django and DRF own backend business behavior

**Status:** Decided
**Decision:** Use Django and Django REST Framework. Core validation, authorization, workflow transitions, approvals, and business rules execute on the backend.
**Consequence:** Client-side state may support drafts and interaction but is not authoritative.

### D-003 — PostgreSQL is the system of record

**Status:** Decided
**Decision:** Persist authoritative business state in PostgreSQL. Redis, OpenAI, browser state, and n8n are not systems of record.
**Consequence:** Asynchronous operations must checkpoint durable state in PostgreSQL.

### D-004 — S3-compatible private object storage

**Status:** Decided
**Decision:** Store source files through an S3-compatible abstraction; DigitalOcean Spaces is the likely production provider. Original files are immutable.
**Consequence:** Database records store object identity, metadata, checksum, and access policy; normal access is authorized and time-limited.

### D-005 — Celery and Redis for background processing

**Status:** Decided
**Decision:** Long-running document and AI work uses Celery with Redis.
**Consequence:** Jobs require durable state, idempotency, retries, failure reporting, and observable progress. Redis must not be the only record of a job outcome.

### D-006 — Structured, task-specific OpenAI use

**Status:** Decided
**Decision:** Use the OpenAI API through narrow task-specific services with schema-validated output. Do not use one unrestricted autonomous agent for the entire workflow.
**Consequence:** Model calls, prompt/schema versions, inputs, and results must be traceable to analysis runs.

### D-007 — Human approval gates downstream use

**Status:** Decided
**Decision:** Findings have explicit review states, and a reviewed intelligence set requires final human approval before later bidding workflows consume it. Confidence never auto-approves.
**Consequence:** Approved data cannot be silently modified, and material reanalysis triggers explicit re-review.

### D-008 — Preserve revisions and provenance

**Status:** Decided
**Decision:** Preserve original files, document revisions, analysis runs, findings, evidence, reviews, and approvals. Do not overwrite history.
**Consequence:** Models use immutable records and explicit supersession where appropriate.

### D-009 — Organization-aware architecture

**Status:** Decided
**Decision:** Begin with one organization, BB Builders Ltd., while scoping production data and authorization by organization. Initial roles are Admin, Estimator / Operator, and Viewer. External users are future scope.
**Consequence:** Organization ownership and membership checks are foundational, even without initial multi-tenant sales behavior.

### D-010 — Django session authentication for the browser

**Status:** Decided
**Decision:** Django authenticates the browser with its server-side session framework and an HttpOnly session cookie. State-changing requests use Django CSRF protection and a readable CSRF cookie; the Next.js frontend sends credentials and the `X-CSRFToken` header. Authentication credentials or bearer tokens are not stored in browser storage. Local development uses exact `127.0.0.1` frontend and backend origins. Production requires HTTPS, secure cookies, explicit trusted origins, and narrowly configured credentialed CORS.
**Consequence:** Django remains the authentication and authorization authority. The frontend session gate improves UX but never replaces API permission checks. Password reset, MFA, and final production domain topology remain later security decisions.

### D-011 — Time handling

**Status:** Decided
**Decision:** Store audit instants in UTC. Give each project a timezone and interpret project deadlines/schedule dates in that timezone. Preserve date-only values as date-only.
**Consequence:** API schemas and UI formatting must distinguish dates from datetimes.

### D-012 — Initial intelligent document formats

**Status:** Decided
**Decision:** Milestone 1 intelligently processes PDF, DOCX, XLSX, and JPG/PNG. Construction drawings are primarily PDF. Other formats may be retained without full parsing; DWG/CAD parsing is not required.
**Consequence:** Upload support and intelligent-processing support are separate capabilities.

### D-013 — Deterministic financial logic

**Status:** Decided
**Decision:** Authoritative financial calculations use deterministic application code. AI may propose or extract inputs but does not serve as the accounting engine.
**Consequence:** Later pricing logic requires explicit formulas, rounding, validation, and tests.

### D-014 — Keep the existing frontend at repository root initially

**Status:** Provisional
**Decision:** Add a future Django backend beside the existing frontend rather than moving the approved frontend immediately.
**Consequence:** This minimizes deployment and path churn. Reconsider only if build/deployment tooling demonstrates a clear need for `/frontend`.

### D-015 — Intelligence conflicts are first-class records

**Status:** Decided
**Decision:** Represent material contradictions with `IntelligenceConflict` records that connect multiple participating findings and/or provenance sources. Resolution outcome, rationale, actor, timestamp, and superseded resolution history are preserved.
**Consequence:** A convenience conflict flag on a finding is not the authoritative conflict model, and competing claims are never discarded by resolution.

### D-016 — Analysis tasks are independently traceable

**Status:** Decided
**Decision:** A complete `AnalysisRun` contains `AnalysisTaskRun` children for narrow classification, indexing, extraction, comparison, and other services. Findings identify the task run that produced them.
**Consequence:** Tasks may succeed, fail, and retry independently while retaining provider/model, prompt, schema, configuration, input, attempt, error, and available usage/cost metadata.

### D-017 — Approval targets an immutable intelligence snapshot

**Status:** Decided
**Decision:** After findings are reviewed and material conflicts resolved, create an immutable `ProjectIntelligenceSnapshot` manifest containing the analysis run, included findings, effective finding reviews, relevant resolved conflicts, version, and hash. `ProjectIntelligenceApproval` references this snapshot, not an analysis run alone.
**Consequence:** Later reviews or analysis cannot cause an existing approval to drift. A different effective state requires a new snapshot and approval.

### D-018 — Explicit current document revision

**Status:** Decided
**Decision:** `Document.current_revision` is the authoritative current-revision reference. Changing it is an explicit, validated, audited backend transition. Upload order, filename, date, and revision label do not select current revision implicitly.
**Consequence:** A new upload remains a preserved candidate revision until the defined workflow makes it current.

### D-019 — Processing-job target integrity

**Status:** Decided
**Decision:** Processing jobs may target only explicitly supported Milestone 1 records such as `FileAsset`, `DocumentRevision`, `DocumentPage`, `AnalysisRun`, and `AnalysisTaskRun`. Avoid an unconstrained polymorphic `GenericForeignKey`; use a design with strong validation and referential integrity.
**Consequence:** Detailed implementation may use explicit foreign keys or controlled target tables, but jobs cannot point to arbitrary domain records.

### D-020 — Milestone 1 prioritizes the end-to-end document journey

**Status:** Decided
**Decision:** Prioritize authenticated project creation, real file preservation, PDF processing/indexing, structured analysis, provenance, review, conflict resolution, snapshot approval, and persistence across logout/reload. PDF construction intelligence receives the deepest processing. Other supported formats receive format-appropriate extraction.
**Consequence:** Use Django Admin initially for basic user/membership administration if appropriate. Advanced operational dashboards, complex retention automation, sophisticated migration, elaborate backup UI, enterprise support tooling, and later workflows must not displace the primary acceptance journey. Safe production baselines remain required.

### D-021 — Acceptance combines invariant tests with a representative package

**Status:** Decided
**Decision:** Automate critical invariant tests for permissions, immutable revisions, job idempotency, provenance, review history, conflict resolution, snapshot approval, and material-revision re-review. The key acceptance demonstration is one representative real or sanitized BB Builders tender package completing the full Milestone 1 journey.
**Consequence:** Broad test coverage is valuable, but milestone acceptance must prove the integrated construction-document workflow rather than only isolated technical components.

### D-022 — M1-01 backend runtime and dependency baseline

**Status:** Decided
**Decision:** Use Python 3.12 or newer with the Django 5.2 LTS line, Django REST Framework 3.18, Celery 5.6, PostgreSQL 17, Redis 7.4, and `django-storages` backed by an S3-compatible service. Pin exact Python package versions in `backend/pyproject.toml` and update them deliberately through tested dependency changes.
**Consequence:** The foundation favors the supported Django LTS line and a small dependency set. OpenAI and document-parsing packages are intentionally deferred until the task that needs them.

### D-023 — Local development service topology

**Status:** Decided
**Decision:** Run PostgreSQL, Redis, and MinIO through Docker Compose while running Next.js, Django, and Celery as local developer processes. MinIO is local-only and its bucket is private by default.
**Consequence:** Local setup remains inspectable and lightweight without committing to a production hosting topology or containerizing the approved frontend.

### D-024 — Explicit organization context for project APIs

**Status:** Decided
**Decision:** Project APIs identify organization context through `/api/v1/organizations/{organization_slug}/...`. Django validates the requested organization against the authenticated user's active membership. The backend never selects a user's first membership and never trusts organization or project ownership supplied in a request payload.
**Consequence:** A user with several memberships has an explicit tenant boundary on every request. Project querysets and nested contact querysets remain scoped to that validated organization and project.

### D-025 — Project identity, archive, and lifecycle policy

**Status:** Decided
**Decision:** Project numbers are case-insensitively unique within an organization while preserving the entered display value. Projects are archived and reactivated through `is_active`; destructive project deletion is not exposed. Archived projects remain listable and retrievable. Only Admin members may change project archive state. Estimator / Operator members may edit ordinary project fields but not `is_active`. Project contacts also use `is_active`, and both Admin and Estimator / Operator members may deactivate or reactivate them. M1-03 validates the controlled project status vocabulary but does not enforce a workflow transition state machine.
**Consequence:** Project history remains recoverable, tenant-specific identifiers cannot differ only by case, and future workflow services may add transition rules without treating the current status field as arbitrary text.

### D-026 — M1-03 project audit boundary

**Status:** Decided
**Decision:** Use a small append-oriented `AuditEvent` for project and project-contact creation, material updates, archive/reactivation, and contact activation changes. API and Django Admin mutations record the authenticated actor, organization, project, target, UTC occurrence time, changed fields, and safely serialized before/after context. Audit records have no product mutation endpoint and are read-only in Django Admin.
**Consequence:** M1-03 provides a reusable minimum business audit trail without event sourcing, signals with hidden request state, middleware-based actor injection, or an Activity UI.

### D-027 — Project deadline and date representation

**Status:** Decided
**Decision:** Project and audit instants are timezone-aware and stored in UTC. Bid and question deadline API inputs require an explicit ISO 8601 UTC offset or `Z`. The project timezone records the local interpretation context. Site visit, planned start, substantial completion, and opening/handover obligations remain date-only fields.
**Consequence:** API clients cannot silently submit ambiguous naive deadlines, and date-only obligations do not shift when rendered in another timezone.

### D-028 — Frontend organization context and production project identity

**Status:** Decided
**Decision:** The Next.js product derives available organization contexts only from active memberships returned by `/api/v1/auth/me/`. One active membership is selected automatically. More than one requires an explicit in-memory user selection; no first-membership fallback is allowed. Zero memberships produces an access state. The selected slug determines API routing but is never authorization proof. `/projects`, project creation, and numeric production-project workspaces use the organization-scoped Django API as their canonical source.
**Consequence:** Frontend navigation remains convenient without duplicating backend authorization or assuming BB Builders ownership. Membership and cross-organization enforcement remain server responsibilities.

### D-029 — Production-project separation and project-local datetime conversion

**Status:** Decided
**Decision:** Historical demo projects remain reachable only through exact fixture IDs. Any other project route is treated as a production identity and must load through the selected organization's API; it never falls back to fixture data. Until later workflow domains exist, production-project tabs show normal empty states rather than demo documents, scopes, bids, or proposals. `datetime-local` form values are interpreted with the project's selected IANA timezone using `Intl.DateTimeFormat`, validated for nonexistent local times, and serialized with an explicit numeric UTC offset. Date-only fields remain unchanged `YYYY-MM-DD` values. Status is displayed but not editable in M1-04 because exposing later lifecycle states would imply workflows that are not production-backed.
**Consequence:** Real projects cannot inherit another project's prototype workflow, and deadline instants do not accidentally use the browser timezone. Archive/reactivate controls are shown only to Admin members; ordinary metadata editing is shown to Admin and Estimator / Operator members, while Viewer UI is read-only. Django remains authoritative for every mutation.

### D-030 — File, project-file, document, and revision separation

**Status:** Decided
**Decision:** Represent a stored binary as an organization-owned immutable `FileAsset`, bind it to exactly one project through `ProjectFile`, represent its logical business identity with `Document`, and preserve every source version as an immutable `DocumentRevision`. Storage keys are globally unique and remain private backend metadata. A revision file must belong to the same project as its document. `Document.current_revision` remains nullable and may change only through the validated, audited `set_current_revision` domain service; creating a revision never selects it implicitly.
**Consequence:** M1-05 can establish durable ownership and history without implementing uploads. Its organization/project-scoped document and revision APIs are read-only metadata views. Upload intents, object writes and verification, upload/validation/malware states, document mutation APIs, and revision-creation workflows remain M1-06 scope. Processing jobs, page/sheet records, and AI behavior remain later tasks.

### D-031 — Backend-mediated private document uploads and downloads

**Status:** Decided
**Decision:** M1-06 uses authenticated Django multipart endpoints to receive browser uploads, stream/hash Django uploaded-file chunks, validate a centralized allowlist and best-effort signatures, and write immutable objects through a small Django-storage adapter. Direct browser-to-S3 presigned upload is deferred until scale demonstrates a need. Object keys use `organizations/{organization_id}/projects/{project_id}/files/{uuid}{extension}` and never use a client path. The configurable `DOCUMENT_UPLOAD_MAX_BYTES` default is 250 MiB. Accepted source extensions are PDF, DOCX, DOC, XLSX, XLS, CSV, TXT, PNG, JPG, and JPEG. SHA-256 is computed from actual uploaded bytes. PDF, PNG, JPEG, OOXML ZIP structure, and legacy OLE signatures receive deterministic best-effort checks; text formats and legacy Office subtypes do not claim strong content identification. Equal checksums remain permitted and no checksum deduplication occurs.
**Consequence:** Object storage is written before the database transaction; database/domain failure triggers best-effort compensating object deletion and cleanup failure is logged without hiding the original error. A new document explicitly selects its first revision through `set_current_revision`. Later revision uploads preserve the current revision unless `make_current` is explicitly true, and an explicit set-current endpoint remains available. The first successful real upload narrowly advances a Draft project to Documents Uploaded and audits that transition; later states are not changed. Authorized downloads stream the private object through Django using the revision relationship, never a client-supplied key or permanent public URL. Direct-to-storage uploads, presigned downloads, resumability, request idempotency, malware scanning, advanced MIME inspection, retention automation, and storage lifecycle tooling remain future scaling or production-hardening work.

### D-032 — Durable revision-targeted source verification

**Status:** Decided
**Decision:** M1-07 introduces a dedicated `processing.ProcessingJob` with one required `DocumentRevision` foreign key and no `GenericForeignKey`. Organization, project, document, file, and immutable source metadata are derived through that exact revision rather than copied into independently drifting columns. The only M1-07 job type is `source_verification`; success means the private source object was streamed and its actual byte count and SHA-256 matched the immutable `FileAsset`. It does not mean the document was parsed, indexed, classified, understood, or analyzed.

PostgreSQL is authoritative for queued, running, succeeded, and failed state. Job creation occurs inside the revision-creation transaction and Celery publication is registered with `transaction.on_commit`. A broker publication failure never rolls back a successful upload: the durable job remains queued for `dispatch_queued_processing_jobs`. A partial database uniqueness constraint prevents more than one queued/running job for the same revision and job type. Celery messages contain only the ProcessingJob ID. Workers atomically claim with row locking, increment attempts, use a five-minute renewable lease, and safely no-op for completed or currently leased jobs. `recover_stale_processing_jobs` returns expired running jobs to queued state without manual database editing.

Celery acknowledges tasks after execution and rejects work on worker loss. Redis visibility timeout is one hour. Storage-unavailable failures retry automatically at 15 and 30 seconds, for at most three total execution attempts. Missing sources and size/checksum mismatches fail immediately until a human requests a new job. Retry creates a new ProcessingJob so prior failure history remains intact. User requests and retries create business `AuditEvent` records; worker claims, heartbeats, transitions, and safe identifiers use operational logs rather than flooding the business audit table. On Windows the supported local command is `.venv/Scripts/celery -A config worker --loglevel=INFO --pool=solo` from `backend`.

**Consequence:** Redis loss cannot erase processing intent, duplicate delivery cannot mutate source records or create duplicate domain objects, and the production Documents UI can truthfully show durable verification state. M1-08 remains responsible for PDF pages, rendering, and sheet indexing. M1-09 remains responsible for structured AI-assisted analysis; neither is implied by successful source verification.

### D-033 — Deterministic native PDF page and sheet indexing

**Status:** Decided
**Decision:** M1-08 uses the explicitly pinned PyMuPDF 1.28.2 dependency to index source-verified PDFs. Every physical PDF page becomes an immutable `DocumentPage` owned by one exact immutable `DocumentRevision`. Page numbers are 1-based; page labels store complete normalized human-readable semantics; width and height use PDF points; rotation records the PDF page rotation in degrees (0, 90, 180, or 270). Some PDFs expose labels as strict `<FEFF...>` UTF-16BE hexadecimal strings, which are deterministically decoded before storage and extraction. Ordinary readable labels remain readable, valid normalized labels are never silently truncated, and malformed encoded/control-bearing values become blank rather than guessed text. Native text is extracted directly from the PDF only. An image-only or scanned page succeeds with blank native text and `has_native_text=false`; M1-08 performs no OCR, vision, or AI interpretation.

`DrawingSheet` is an optional one-to-one candidate attached to a page, not a synonym for every PDF page. Sheet number and title extraction is deterministic and conservative. A clearly structured decoded label ending in `title-sheet number` is strong page-label evidence; the terminal sheet token is authoritative because it is the label's explicit identifier, while earlier sheet-like tokens are treated as context. Explicitly labeled native-text fields are next in precedence. The weak native-text fallback requires exactly one standalone sheet token and an immediately adjacent recognizable title, so drawing-register entries elsewhere on the page cannot be mistaken for the current sheet title. Strong page-label evidence cannot be overridden by weaker whole-page text. Ambiguous evidence remains blank. Filenames never provide sheet identity, and the indexer does not infer discipline or trade. Quality is a deterministic evidence classification (`high` or `medium`), not model confidence.

PDF indexing requires a successful source-verification job and is automatically chained as a separate durable `pdf_indexing` job only for assets whose verified detected MIME type is `application/pdf`. Job publication remains transaction-on-commit and broker-failure safe. Page persistence is atomic and revision scoped: an incomplete attempt is replaced during a successful retry, successful redelivery is a no-op, and a successful historical-revision index is not casually rebuilt or overwritten by indexing another revision.

Workers stream the private object to a uniquely named temporary PDF because PyMuPDF requires seekable local access. Temporary paths are never persisted, and cleanup is attempted on success, parser failure, source read failure, and source close failure without allowing cleanup errors to hide the primary processing failure. Missing, non-PDF, encrypted, corrupt, storage-unavailable, and unexpected indexing outcomes use controlled safe errors. Encrypted PDFs are not decrypted or bypassed.

Page APIs are read-only and organization/project/document/revision scoped. List and detail payloads expose page metadata, native-text availability/count, and optional sheet identity, but never return full native text, bucket, object key, credentials, or storage URLs. Indexing does not advance project status; the project remains `documents_uploaded`. M1-09 owns AI-assisted document understanding, OCR/vision decisions, provenance, findings, conflicts, and intelligence workflow.

The Documents UI treats a source-verified eligible PDF with no visible indexing job as a bounded chaining transition rather than immediately presenting an explicit indexing action. It refetches three times at five-second intervals after the first missing-job observation. If the durable chained job appears, its backend state becomes authoritative; otherwise the UI settles on the historical `PDF not yet indexed` state. This prevents a short source-completion/chained-job visibility race without polling indefinitely, creating jobs from the browser, or hiding a persisted failure.

**Consequence:** M1-08 creates a reproducible physical-page foundation without presenting deterministic extraction as AI understanding or fabricating drawing metadata when source evidence is weak.

### D-034 — Explicit, versioned structured machine analysis

**Status:** Decided

**Decision:** M1-09 introduces an environment-selected backend provider through a narrow analysis-provider interface. The initial production implementation uses the OpenAI Responses API and tests use a deterministic fake provider with no network access. Provider credentials remain environment-only and are never stored in PostgreSQL or sent to the browser. Paid analysis is initiated only by an authorized explicit request; upload, source verification, and PDF indexing never trigger it automatically.

Each request creates a durable immutable `AnalysisRun` for one exact `DocumentRevision`, followed by one `AnalysisTaskRun` per indexed `DocumentPage` and one document-synthesis task. PostgreSQL owns run/task state and Celery transports only the durable run ID. One active run per revision, transactional creation, row-locked claims, leases, bounded retries, succeeded-task no-ops, and explicit new runs for reanalysis preserve history and control concurrency. Old results are never overwritten.

Page tasks execute sequentially beneath one run-level database claim. A valid run lease prevents a second worker from claiming the same run. Transient provider timeout, rate-limit, and availability failures return the affected task and run to durable queued state, then Celery schedules the next delivery after `AI_RETRY_BASE_SECONDS * 2^(attempt-1)`. PostgreSQL attempt counts enforce the task maximum; a recovered stale task at its limit fails safely rather than receiving another provider call. Terminal configuration, schema, provider-rejection, and rendering failures are not retried. Queued redispatch is idempotent within its dispatch window, and stale recovery never touches succeeded or non-stale runs.

Page routing is deterministic: text pages use the indexed `DocumentPage.native_text`; deterministic `DrawingSheet` pages use native text plus an exact bounded temporary page render; pages without native text use the page render. Native text is not reparsed and truncation is recorded. Temporary PDF/PNG artifacts are removed on success and failure. M1-09 performs no OCR and does not use filenames as analytical evidence.

Prompts are centralized and versioned. Page and synthesis results are validated against versioned Pydantic schemas before persistence. Material candidates carry exact page IDs/numbers, optional deterministic sheet IDs/numbers, and bounded text or visual evidence. Document synthesis consumes validated page JSON rather than resending the PDF. Malformed responses fail with controlled errors. Usage metadata is stored only when returned; currency cost is never fabricated. Configurable page, native-text, render-dimension, and retry limits bound cost.

Starting the first eligible run advances a project from `documents_uploaded` to `ai_analysis` and records that transition, without regressing later states or entering `human_scope_review`. Business audit events record request, retry request, and completion without page-level noise. The UI clearly labels every result **Machine generated — not yet human reviewed** and offers no approval controls.

Authenticated manual validation used the deterministic fake provider with real PostgreSQL, Redis, Celery, MinIO, Django, and Next.js. It confirmed persisted structured results and evidence, immutable run/task history, explicit `Run AI Analysis Again` behavior, and durable browser-created queued intent while the worker was stopped. Restarting Celery naturally consumed the same queued run without manual retry or redispatch. No live OpenAI request was part of M1-09 implementation acceptance; live-provider testing requires separate authorization.

M1-10 owns promotion into first-class `ExtractedFinding` and `FindingSource` records, formal provenance, `FindingReview`, and `IntelligenceConflict`. M1-11 owns immutable intelligence snapshots and human approval. An M1-09 machine payload is never approved project truth.

**Consequence:** M1-09 provides durable, inspectable machine interpretation with predictable paid-operation and evidence boundaries while leaving human review and downstream authority to the planned later tasks.

### D-035 — Deterministic finding materialization and append-only human review

**Status:** Decided

**Decision:** M1-10 materializes only the schema-validated synthesis candidates already persisted on an explicitly selected successful `AnalysisRun`. The synchronous transaction makes no provider, OCR, rendering, storage, or document-parsing call. A SHA-256 key over canonical candidate JSON identifies each candidate within its run, and database uniqueness makes repeated or concurrent materialization repeat-safe. Findings from later runs form separate review sets and never overwrite earlier runs or reviews.

`ExtractedFinding` preserves the original category, subject, machine value, support level, schema version, producing synthesis task, exact revision, and conservative semantic key. Human decisions never modify that machine value. `FindingSource` is immutable provenance for an exact page-analysis task, revision, page, optional sheet, and bounded native-text excerpt or visual description. Native excerpts must occur in the persisted indexed page text; visual evidence cannot pretend to be native text.

`FindingReview` is append-only. Accepted uses the machine value, Edited / Accepted stores a separate bounded reviewed value, Rejected preserves the finding without an effective value, and Needs Clarification remains unresolved. Every materially different later decision explicitly supersedes the previous review while retaining the complete history and reviewer attribution. An exact consecutive duplicate of the normalized decision, reviewed value, and note is an idempotent no-op: surrounding whitespace is trimmed, blank and null text compare consistently, and meaningful internal text is preserved. The existing effective review is returned without another review or audit event.

Conflict detection is deterministic and deliberately conservative. A semantic key combines the controlled finding category with a normalized subject key because M1-09 does not yet emit a separate semantic identifier. Only comparable categories participate. Whitespace/case normalization is safe for simple values; ISO-like dates retain canonical components; ambiguous prose is not aggressively typed or financially interpreted. Equivalent values are supporting duplicates, while materially different values sharing a semantic key create one participant-keyed conflict per run. Conflict resolution and dismissal create immutable superseding conflict versions instead of rewriting detection history or selecting a winning finding.

Preparing the first successful run for review advances only `ai_analysis` to `human_scope_review` and records the transition. Unauthorized or failed materialization does not change status, and later states are never regressed. Materialization, review decisions, conflict detection, and conflict resolution use business-level audit events. M1-10 makes zero AI calls.

M1-11 exclusively owns `ProjectIntelligenceSnapshot`, readiness assembly, `ProjectIntelligenceApproval`, and final approval. Reviewed findings are explicitly labelled **Human reviewed — not yet approved project intelligence** and cannot feed later bidding workflows yet.

**Consequence:** Machine evidence, human judgment, and conflict history remain independently attributable and durable, while final project-intelligence authority remains outside M1-10.

Authenticated browser validation confirmed the production review workspace for Admin/Estimator and read-only access for a disposable local Viewer. Machine values and exact page/sheet provenance remained unchanged, reviewed values remained separate, history survived refresh and reauthentication, redundant same-state actions were protected, and the project remained at `human_scope_review`. No provider call or API credit was used.

### D-036 — Project-level intelligence snapshots and approval policy

**Status:** Decided

**Decision:** An M1-11 `ProjectIntelligenceSnapshot` is project-level and may combine one or more explicitly selected successful `AnalysisRun` records from different current document revisions in the same project. Selection is by run ID; the server includes each selected run's complete materialized finding set. Only one run per revision may participate, and each revision must be its document's explicit current revision when the snapshot is created. Normalized source and entry records freeze run, revision, finding, exact effective review, and provenance identities alongside a canonical structured manifest and SHA-256 fingerprint. Rejected findings remain frozen history but are excluded from approved values; unreviewed or needs-clarification findings, missing provenance, and applicable open conflicts block creation and approval.

Admin and Estimator / Operator memberships may create and explicitly approve an exact immutable snapshot, including their own reviewed work. Viewer memberships remain read-only. Repeating an equivalent creation or approval is idempotent. An unapproved snapshot whose current reviewed/source state differs from its frozen fingerprint is stale and cannot be approved; approved historical records are never rewritten by later reviews or revisions.

Approval remains represented by immutable snapshot/approval history and leaves the project at `human_scope_review`. M1-11 creates no trade packages and cannot move the project to `trade_packages_ready`; Milestone 2 owns that work and transition. M1-11 makes no AI/provider, OCR, vision, rendering, or financial-calculation call.

**Consequence:** Approved project intelligence can cover several tender documents without arbitrary historical-run mixing or finding cherry-picking, while preserving exact evidence and maintaining the Milestone 2 boundary.

### D-037 — Safe project activity feed boundary

**Status:** Decided

**Decision:** Milestone 1 exposes project audit history through an organization- and project-scoped, paginated, read-only API. Active Admin, Estimator / Operator, and Viewer memberships may read safe event identity, action code, target reference, actor display name, and timestamp. The general project Activity feed does not expose raw `AuditEvent.metadata`; detailed before/after values may include business or contact information and require a future privileged audit/export policy. No product API may create, update, or delete audit events.

**Consequence:** Users can verify meaningful production workflow history without turning the Activity tab into an administrative data-export surface or weakening the append-only audit boundary. Audit retention, tamper evidence, export, and privileged metadata access remain unresolved deployment decisions under U-012.

### D-038 — Translate technical workflow state at the presentation boundary

**Status:** Decided

**Decision:** The normal production UI describes document processing and human control in construction/business language. Backend terms such as `ProcessingJob`, `AnalysisRun`, `ExtractedFinding`, and `ProjectIntelligenceSnapshot` remain unchanged and authoritative, while the UI presents Prepared documents, AI-assisted Document Review, review items, source locations, and Project Information Versions. Technical identifiers and diagnostics remain available under collapsed Advanced details. Presentation helpers deterministically map persisted state; they do not create a second workflow state machine.

**Consequence:** Non-technical BB Builders users can understand what happened, what needs attention, where information came from, and what approval preserves without weakening provenance, append-only history, permissions, or auditability.

### D-039 — Stable project workflow navigation

**Status:** Decided

**Decision:** The horizontal project workflow tabs are stable product navigation: Overview, Documents, Document Review, Scopes, Contractors, Outreach, Bids, Comparisons, Proposal, and Activity. Milestone or usability work may improve the content inside a tab but must not casually remove, replace, hide, or restructure the complete workflow navigation. The global application sidebar remains a separate navigation layer.

Normal user-facing screens should answer three questions without requiring backend terminology: **What am I looking at? What happened? What do I need to do next?** Technical concepts remain available for support and audit use without becoming required knowledge for normal BB Builders users.

**Consequence:** The end-to-end bidding workflow remains visible and predictable as later milestones replace placeholders, while individual screens can become easier to understand without destabilizing product information architecture.

## Unresolved decisions

### U-001 — Production hosting topology

Define the frontend host, Django runtime, worker runtime, managed PostgreSQL, Redis, networking, TLS termination, secrets management, environments, and deployment promotion strategy.

### U-002 — DigitalOcean Spaces configuration

Select region, bucket separation by environment, object-key convention, encryption settings, CORS, access policy, lifecycle policy, and backup/replication expectations.

### U-004 — Upload limits and behavior

Set per-file and per-project limits, concurrent upload behavior, multipart thresholds, accepted MIME/extension policy, checksum approach, resumability, duplicate detection, and user-facing failure handling.

### U-005 — Malware scanning

Choose scanning service/tooling, quarantine state, timeout/failure policy, who may override a result, and whether processing begins before a clean verdict.

### U-006 — OpenAI model selection

Select models per task after representative construction-document evaluation. Define fallback behavior, cost/latency targets, region/privacy requirements, and model-change approval.

### U-007 — Confidence presentation

Determine calibration method and UI thresholds for low/medium/high presentation by finding category. Thresholds must not produce automatic approval.

### U-008 — Derived-artifact retention

Define retention and regeneration policy for page renders, thumbnails, OCR output, extracted text, embeddings if later approved, and temporary worker files.

### U-010 — Material-change and re-review rules

Define how the system determines that a new document revision or analysis materially affects approved intelligence and the granularity of required re-review.

### U-011 — Document classification taxonomy

Finalize controlled document types, discipline codes, revision labels, addendum relationships, and treatment of combined files containing several logical documents.

### U-012 — Audit retention and access

Set retention period, administrator visibility, export needs, personally identifiable information policy, and tamper-evidence requirements.

### U-013 — Historical data migration

Decide whether Milestone 1 imports existing BB Builders projects/documents or begins with newly created production projects only.

### U-014 — Operational observability

Choose error reporting, metrics, structured logging, tracing/correlation, alert thresholds, and support ownership.

### U-015 — Backup, recovery, and deletion policy

Define database recovery objectives, object-storage recovery, legal/business retention, soft deletion, user-requested deletion, and organization offboarding.

### U-016 — Evidence excerpt storage

Decide whether bounded textual evidence and image crops are persisted, regenerated, or both, considering copyright, security, storage, and reproducibility.

## Required ADRs before affected production coding

At minimum, create focused ADRs for authentication, storage/upload security, processing idempotency, analysis/finding versioning, and approval readiness before those areas are finalized.
