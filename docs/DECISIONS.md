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

### U-009 — Approval readiness policy

Define which finding categories are mandatory, which unresolved items block snapshot creation or final approval, which roles may approve, and whether self-approval is permitted.

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
