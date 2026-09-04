# Milestone 1 Acceptance Record

## 1. Milestone objective

Milestone 1 establishes the production foundation for authenticated project intake, private immutable tender documents, durable processing, deterministic PDF page/sheet indexing, structured AI-assisted interpretation, exact provenance, append-only human review, immutable project-intelligence snapshots, explicit approval, and audit-friendly history.

This record distinguishes automated evidence, previously accepted manual evidence, genuine BB Builders source evidence, and remaining production/UAT prerequisites. It does not claim that unperformed tests passed.

## 2. Contracted boundary

Milestone 1 ends at explicitly approved project intelligence. The project remains `human_scope_review`; no M1 action transitions it to `trade_packages_ready`.

Scope/trade-package generation, subcontractor data and discovery, RFQ/outreach, bid intake/leveling, proposal/award workflows, and project-management synchronization belong to Milestones 2–5 and are not implemented by M1-12.

## 3. Completed implementation tasks

| Task | Delivered capability | Acceptance status |
| --- | --- | --- |
| M1-01 | Django/DRF, PostgreSQL, Redis, Celery, S3-compatible storage foundation and health endpoint | Automated and manually verified |
| M1-02 | Organization-aware session authentication, CSRF/CORS controls, roles and permissions | Automated and manually verified |
| M1-03 | Persistent organization-scoped Project, ProjectContact and AuditEvent domain/API | Automated and manually verified |
| M1-04 | Numeric production project UI connected to Django without fixture fallback | Automated and manually verified |
| M1-05 | Immutable FileAsset, ProjectFile, Document and DocumentRevision model | Automated and manually verified |
| M1-06 | Secure upload/download, private object storage and explicit revision control | Automated and manually verified |
| M1-07 | Durable source-verification processing and worker recovery | Automated and manually verified |
| M1-08 | Native PDF page/sheet indexing with revision isolation | Automated, manually and real-data verified |
| M1-09 | Versioned structured analysis with fake/live provider abstraction | Automated and fake-provider manually verified |
| M1-10 | Immutable findings/provenance and append-only human review/conflict handling | Automated and manually verified |
| M1-11 | Deterministic immutable intelligence snapshot and explicit approval | Automated and manually verified |
| M1-12 | Milestone audit, safe production Activity feed, real-evidence review and acceptance documentation | Automated and manually verified |

## 4. Architecture summary

- Next.js 16 and TypeScript provide the production project workspace while preserving the approved demo routes separately.
- Django 5.2 and Django REST Framework own authorization, validation, workflow transitions, audit creation, and business invariants.
- PostgreSQL is the system of record; Redis is the Celery broker/result backend; private MinIO represents local S3-compatible storage.
- Celery jobs receive durable IDs, while PostgreSQL remains authoritative for status and retry/recovery state.
- PyMuPDF performs deterministic native PDF extraction/indexing. No OCR is currently implemented.
- AI output is schema-validated and versioned; deterministic server code—not AI—controls materialization, readiness, fingerprinting, and approval.
- Machine output, human decisions, approved intelligence, and source provenance remain separate and immutable where required.

## 5. End-to-end workflow validated

Previously accepted local validation demonstrated:

1. Session login and explicit organization selection.
2. Persistent project creation/edit/archive/reactivate with timezone-safe deadlines.
3. Private upload to MinIO with checksum, size, detected MIME, immutable file identity, logical documents and revisions.
4. Durable source verification and automatic eligible PDF-index job chaining through worker downtime/restart.
5. Native page/sheet indexing of an eight-page genuine BB Builders mechanical IFC drawing set.
6. Explicit deterministic fake-provider analysis with eight page tasks and one synthesis task.
7. Idempotent finding materialization, exact page/sheet provenance, and all four append-only review outcomes.
8. Deterministic readiness, immutable Snapshot V1, explicit approval, and stale-draft approval rejection.
9. Viewer read-only behavior and state persistence after refresh and logout/login.
10. Preservation of all historical revisions, runs, findings, reviews, snapshots, and approval records.

The focused M1-12 Activity validation was accepted after restarting the stopped/stale Next.js development server from the current working tree. Numeric Project 2 rendered the production Activity feed; the backend returned 97 project-scoped events and excluded raw audit metadata. No routing or implementation correction was required.

## 6. Automated validation summary

Final implementation-stage validation passed:

- 37 focused project/API tests, including the new Activity endpoint;
- 60 analysis tests;
- 264 full backend tests;
- Ruff formatting and linting;
- Django system check and `makemigrations --check --dry-run`;
- all current local PostgreSQL migrations applied;
- all migrations applied successfully from zero to a temporary fresh PostgreSQL database, followed by a clean Django check and removal of only that temporary database;
- 29 frontend state tests;
- strict TypeScript and ESLint;
- Next.js production build with 66 static pages generated;
- `git diff --check`, ignored `backend/.env`, secret-pattern sanity review, and tracked customer/generated-artifact review.

The frontend state-test runner reports Node's known module-type performance warning because the package does not declare ESM; all 29 tests pass. No migration was added by M1-12.

## 7. Manual validation summary

Accepted M1-01 through M1-11 evidence includes healthy local infrastructure, real PostgreSQL persistence, secure MinIO upload/download, worker restart durability, genuine PDF indexing, fake-provider analysis, human review, snapshot approval, stale protection, Viewer permissions, and logout/login persistence.

M1-12 manual acceptance confirmed the production Activity tab for numeric Project 2, no fixture activity fallback, Viewer read-only access, a project/organization-scoped GET-only API, and exclusion of raw audit metadata. The initially observed placeholder came from a stopped/stale Next.js development server rather than a routing or implementation defect.

## 8. Real BB Builders evidence used

Private local historical evidence was reviewed in place and was not copied into Git. Representative evidence includes:

- JD Sports Intercity mechanical IFC drawings — 8 pages, native text, previously uploaded/indexed and manually compared;
- JD Sports Intercity architectural IFC drawings — 29 pages with native drawing text;
- JD Sports Intercity electrical IFC drawings — 13 pages with native drawing text;
- JD Sports Intercity structural tender drawings — 8 pages with native drawing text;
- JD Sports construction scope of work — 35 pages;
- Intercity Shopping Centre tenant design criteria — 37 pages.

Customer contents, extracted text dumps, page renders, and source binaries remain outside the repository.

## 9. Permissions and security validation

Automated coverage enforces unauthenticated denial, inactive-membership denial, organization/project/document/revision ownership, Viewer mutation denial, unforgeable ownership, private backend-mediated downloads, CSRF/session controls, safe client errors, and read-only historical APIs. Storage bucket/key/credentials, backend secrets, unrestricted native page text, and raw provider responses are not exposed to the browser.

The M1-12 project Activity endpoint is read-only and project scoped. It exposes safe event identity/actor/time fields but not raw audit metadata. Production deployment still requires final hosting, TLS, secret-management, malware-scanning, retention, backup, monitoring, and privileged audit-access policies.

## 10. Revision and history validation

Original FileAssets and every DocumentRevision are preserved. `Document.current_revision` changes only through the explicit controlled service. Page indexes, runs, findings and snapshots remain revision-specific. Historical revisions cannot create new snapshots; later reviews or revisions cannot mutate a previously approved snapshot or approval. Existing local Project 2 validation history is intentional and must not be cleaned up.

## 11. AI-provider validation status

All automated and manual M1 analysis validation used the deterministic network-free fake provider. No live OpenAI request was performed and no OpenAI API credit was consumed.

Static review confirms that the production adapter uses the Responses API, `store: false`, strict JSON Schema output, text and image input blocks, bounded timeout, safe HTTP/network error mapping, and token-usage parsing. Mocked tests cover request/response parsing but cannot prove live model/schema compatibility, account/model access, provider-side error variants, latency, or real construction-document quality.

**LIVE_PROVIDER_SMOKE_RECOMMENDED** before production acceptance. Use one current, source-verified/indexed native-text PDF revision with at most one page selected in a dedicated non-production project. Expect one page-analysis request and one synthesis request (two provider requests total), with no vision image. Verify model access, accepted request shape, strict schema response, `store: false`, request IDs, token metadata, safe failure mapping, durable task completion, and zero browser exposure of credentials/provider payload. This requires separate explicit authorization and backend-only secret configuration.

## 12. Known limitations

- Scanned/image-only PDF pages can be indexed and routed to visual analysis, but M1 has no OCR text layer.
- Live OpenAI compatibility and result quality have not been validated.
- Structured deep intelligence is currently PDF-only; allowed DOCX/XLSX/image uploads are retained and source-verified but do not receive equivalent extraction/analysis depth.
- Conflict detection is deliberately conservative and based on current controlled categories/semantic keys; broader cross-run/domain reconciliation remains future evaluation work.
- Material-change/re-review policy is enforced through current-revision and stale-fingerprint boundaries, but finer-grained impact analysis is unresolved.
- Production cloud deployment, object-storage lifecycle, malware scanning, observability, backups/recovery, audit retention/export, and calibrated confidence thresholds remain deployment/ADR work.
- Later milestone procurement, bid, proposal, award, and integration functionality remains demo-only or unimplemented on numeric production projects.

## 13. Explicit Milestone 2 boundary

No M1-12 code creates scopes, trade taxonomies, trade packages, subcontractors, shortlists, outreach, bids, proposals, awards, or integrations. Approved intelligence is the only M1 handoff artifact. Milestone 2 remains not started.

## 14. Remaining deployment and UAT prerequisites

1. Perform the separately authorized minimal live-provider compatibility smoke test in staging/UAT.
2. Select production hosting, database, Redis, object-storage, TLS and secret-management topology.
3. Decide upload limits, malware/quarantine behavior, storage lifecycle, backup/recovery and audit retention/export policy.
4. Configure production observability, alerts and support ownership.
5. Run representative BB Builders UAT with approved private data-handling procedures and chosen models.

## 15. Final milestone acceptance checklist

- [x] M1-01 through M1-11 implementation and task-level manual validation completed.
- [x] Genuine BB Builders PDF drawing evidence indexed and compared without committing customer files.
- [x] Full production path reaches immutable explicitly approved project intelligence.
- [x] Historical revisions, analysis, reviews, snapshots and approvals remain preserved.
- [x] Role, organization and project boundaries have automated coverage.
- [x] No Milestone 2 domain implementation is present.
- [x] Final M1-12 Activity/persistence manual check accepted.
- [x] Final automated command results recorded in the implementation handoff.
- [ ] `LIVE_PROVIDER_SMOKE_RECOMMENDED` remains a staging/UAT prerequisite; live compatibility is not proven.
- [ ] Production deployment/security/operations decisions completed before launch.
