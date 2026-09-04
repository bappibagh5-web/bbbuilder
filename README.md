# BB Builders AI Bid Automation System

This repository contains the approved Next.js frontend demonstration and the production backend foundation for the BB Builders AI Bid Automation System.

Milestone 1 implementation is intentionally incremental. The existing demo remains the UX baseline and still uses deterministic fixture data until later Milestone 1 tasks connect individual workflows to production APIs.

## Permanent project memory

If conversation history is unavailable, recover project context from the committed repository before changing code. Start with `docs/AI_HANDOFF.md` for the cross-chat/account recovery procedure, then use `docs/PROJECT_CONTEXT.md`, `docs/ROADMAP.md`, `docs/CURRENT_STATUS.md`, and `docs/DECISIONS.md` as their described canonical sources. Inspect recent Git history and the current status/diff before continuing work. The shorthand **Sync BB Builders** requests this read-only recovery.

## Demo workflow

Project Intake → Documents → AI Review → Trade Scopes → Bid Packages → Contractor Discovery → Outreach → Bid Intake → Bid Comparison → Client Proposal → Awarded Project

The primary walkthrough follows project **BB-2026-041 — Retail Store Tenant Improvement**. After starting the application, open the dashboard and use **Demo Guide** for quick navigation through the recommended presentation sequence.

## Technology

- Frontend: Next.js, TypeScript, React, and Tailwind CSS
- Backend: Django and Django REST Framework
- Database: PostgreSQL
- Background processing foundation: Celery and Redis
- Local object storage: MinIO through an S3-compatible interface

## Prerequisites

- Node.js compatible with the version in `package.json`
- npm
- Python 3.12 or newer
- Docker Desktop or Docker Engine with Compose

MinIO is for local development only. Production object-storage topology remains an explicit architecture decision.

## Environment setup

Copy the safe example files and replace backend local placeholder passwords. Keep `backend/.env` and `.env.local` untracked.

PowerShell:

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item .env.example .env.local
```

POSIX shell:

```bash
cp backend/.env.example backend/.env
cp .env.example .env.local
```

The backend file supplies Django configuration and Docker Compose service credentials. Ensure `DATABASE_URL`, the `POSTGRES_*` values, and the MinIO/S3 credentials agree. The root frontend file sets `NEXT_PUBLIC_API_BASE_URL`; use the same hostname (`127.0.0.1`) for both applications so session and CSRF cookies behave consistently.

`DOCUMENT_UPLOAD_MAX_BYTES` controls the maximum accepted source-document size. The tracked local example uses 262,144,000 bytes (250 MiB), which is large enough for typical commercial drawing packages while remaining bounded.

## Start local infrastructure

From the repository root:

```bash
docker compose --env-file backend/.env -f infra/compose.yaml up -d
docker compose --env-file backend/.env -f infra/compose.yaml ps
```

Compose starts PostgreSQL, Redis, MinIO, and a one-time job that creates a private local bucket.

## Create the Python environment

PowerShell:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install --upgrade pip
backend/.venv/Scripts/python -m pip install -e "backend[dev]"
```

POSIX shell:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -e 'backend[dev]'
```

## Initialize and run Django

PowerShell:

```powershell
backend/.venv/Scripts/python backend/manage.py migrate
backend/.venv/Scripts/python backend/manage.py createsuperuser
backend/.venv/Scripts/python backend/manage.py bootstrap_organization --email admin@example.com --name "BB Builders Ltd." --legal-name "BB Builders Ltd." --slug bb-builders --role admin
backend/.venv/Scripts/python backend/manage.py runserver 127.0.0.1:8000
```

POSIX shell:

```bash
backend/.venv/bin/python backend/manage.py migrate
backend/.venv/bin/python backend/manage.py createsuperuser
backend/.venv/bin/python backend/manage.py bootstrap_organization --email admin@example.com --name "BB Builders Ltd." --legal-name "BB Builders Ltd." --slug bb-builders --role admin
backend/.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```

The health endpoint is available at `http://127.0.0.1:8000/api/v1/health/` and returns:

```json
{"status": "ok"}
```

PowerShell verification:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/
```

Choose your own email and password when running `createsuperuser`; no credentials are included in the repository. The idempotent `bootstrap_organization` command creates or updates the organization and active membership for that existing user. Initial user, organization, and membership administration is also available at `http://127.0.0.1:8000/admin/`.

### Required one-time M1-02 local database reset

M1-01 applied Django's built-in authentication migrations before the custom user model was introduced. Django requires a custom user model to exist in the initial migration history. Existing M1-01 local development databases must therefore be recreated once before applying M1-02 migrations. This is a development-only destructive action; back up anything you need first. The current M1-01 volume contains no production domain data.

From the repository root, after confirming `backend/.env` points only to the disposable local Compose services:

```bash
docker compose --env-file backend/.env -f infra/compose.yaml down -v
docker compose --env-file backend/.env -f infra/compose.yaml up -d
backend/.venv/Scripts/python backend/manage.py migrate
backend/.venv/Scripts/python backend/manage.py createsuperuser
backend/.venv/Scripts/python backend/manage.py bootstrap_organization --email admin@example.com --name "BB Builders Ltd." --legal-name "BB Builders Ltd." --slug bb-builders --role admin
```

`down -v` removes the Compose project's local PostgreSQL, Redis, and MinIO volumes. Never run this procedure against shared or production infrastructure. The application does not perform this reset automatically.

## Start Celery

M1-07 adds durable source-verification jobs. PostgreSQL owns job intent and state; Redis transports Celery messages. The worker streams immutable source objects and verifies byte size and SHA-256 only. It does not parse PDFs, index pages, or run AI.

Windows PowerShell:

```powershell
Set-Location backend
.venv/Scripts/celery -A config worker --loglevel=INFO --pool=solo
```

macOS/Linux:

```bash
cd backend
.venv/bin/celery -A config worker --loglevel=INFO
```

Queued work remains durable if the worker or broker is unavailable. Operational recovery commands from `backend/` are:

```bash
python manage.py dispatch_queued_processing_jobs
python manage.py recover_stale_processing_jobs
```

The first republishes queued jobs that were not recently dispatched. The second re-queues expired running leases and dispatches them through the normal service. Both commands are idempotent and expose no storage credentials.

## Start the existing frontend

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. The root route redirects to the dashboard. Sign in with the user created above. M1-02 authenticates the application shell, but it does not replace frontend project fixtures or connect project screens to backend APIs.

## Browser authentication

The frontend uses Django session authentication. The session identifier is held in an HttpOnly cookie and state-changing requests require a Django CSRF token. API requests include browser credentials; there are no JWTs or authentication tokens in `localStorage` or `sessionStorage`.

The local frontend and API origins must match `FRONTEND_ORIGIN`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` in `backend/.env`. CORS is credentialed and exact-origin only. Production settings require HTTPS secure cookies and reject wildcard CORS/trusted-origin configuration.

Auth endpoints:

- `GET /api/v1/auth/csrf/`
- `POST /api/v1/auth/login/`
- `POST /api/v1/auth/logout/`
- `GET /api/v1/auth/me/`

## Project API

M1-03 provides persistent organization-scoped projects and project contacts. M1-04 connects `/projects`, project creation, and production project workspaces to these endpoints. Historical fixture projects remain available only through their explicit demo IDs for the later prototype workflows.

Authenticated project endpoints use an explicit organization slug:

```text
GET/POST  /api/v1/organizations/{organization_slug}/projects/
GET/PUT/PATCH  /api/v1/organizations/{organization_slug}/projects/{project_id}/
GET/POST  /api/v1/organizations/{organization_slug}/projects/{project_id}/contacts/
GET/PUT/PATCH  /api/v1/organizations/{organization_slug}/projects/{project_id}/contacts/{contact_id}/
```

Project ownership and nested contact ownership are assigned from the validated URL context, not request-body identifiers. Project deletion is unavailable; Admin members archive or reactivate by patching `is_active`. Estimator / Operator members may edit ordinary project fields and manage contact activation but cannot change project archive state. Viewer members are read-only.

Bid and question deadlines require an explicit ISO 8601 offset, for example `2026-09-15T14:30:00-04:00` or `2026-09-15T18:30:00Z`. Date-only project milestones use `YYYY-MM-DD`.

Project and contact collections use page-number pagination with 50 records by default and a maximum requested page size of 100.

The frontend derives organization context from the active memberships returned by `/api/v1/auth/me/`. A single membership is selected automatically; users with several memberships must explicitly choose one. Project-local deadline inputs are converted with the selected IANA project timezone and sent with an explicit UTC offset. Production project workflow tabs show honest empty states until their corresponding backend domains are implemented; they never fall back to another project's fixture records.

## Project document upload API

M1-06 connects numeric production-project Documents tabs to authenticated private object storage. Django receives multipart uploads, computes SHA-256 using uploaded-file chunks, validates the centralized extension/MIME/signature policy, generates a UUID-based immutable object key, stores the source in the configured S3-compatible bucket, and creates the file/document/revision records transactionally. Uploaded bytes are not parsed or sent to any processing or AI service in M1-06.

```text
POST  /api/v1/organizations/{organization_slug}/projects/{project_id}/documents/upload/
POST  /api/v1/organizations/{organization_slug}/projects/{project_id}/documents/{document_id}/revisions/upload/
POST  /api/v1/organizations/{organization_slug}/projects/{project_id}/documents/{document_id}/revisions/{revision_id}/set-current/
GET   /api/v1/organizations/{organization_slug}/projects/{project_id}/documents/{document_id}/revisions/{revision_id}/download/
```

Supported upload extensions are PDF, DOCX, DOC, XLSX, XLS, CSV, TXT, PNG, JPG, and JPEG. The backend remains authoritative; the browser `accept` attribute is only a convenience. Downloads are authorized and streamed through Django without exposing the bucket, object key, credentials, or a permanent public URL. Malware scanning, resumable/direct-to-storage uploads, advanced file identification, and retention automation remain future production-hardening decisions.

## Source-verification processing API

Every newly persisted document revision receives a durable queued source-verification job. Existing revisions can be explicitly requested. Admin and Estimator / Operator members may request or retry; Viewer members are read-only.

```text
GET   /api/v1/organizations/{organization_slug}/projects/{project_id}/documents/{document_id}/revisions/{revision_id}/processing-jobs/
POST  /api/v1/organizations/{organization_slug}/projects/{project_id}/documents/{document_id}/revisions/{revision_id}/process/
POST  /api/v1/organizations/{organization_slug}/projects/{project_id}/processing-jobs/{job_id}/retry/
```

User-facing states are Queued, Verifying source, Source verified, and Verification failed. Source verification never advances the project to AI Analysis and does not create pages, sheets, extracted text, or findings.

## PDF page and sheet indexing API

After a PDF source passes source verification, the processing service automatically creates a durable `pdf_indexing` job. Admin and Estimator / Operator members may explicitly request or retry indexing; Viewer members may read processing and page metadata. Non-PDF revisions do not receive PDF-indexing jobs or controls.

```text
POST  /api/v1/organizations/{organization_slug}/projects/{project_id}/documents/{document_id}/revisions/{revision_id}/index-pdf/
GET   /api/v1/organizations/{organization_slug}/projects/{project_id}/documents/{document_id}/revisions/{revision_id}/pages/
GET   /api/v1/organizations/{organization_slug}/projects/{project_id}/documents/{document_id}/revisions/{revision_id}/pages/{page_id}/
```

The Celery worker command is unchanged. PyMuPDF 1.28.2 streams each private source to a temporary seekable PDF, records 1-based page numbers, normalized human-readable PDF labels, point dimensions, rotation, and native PDF text, then removes the temporary file. Strict `<FEFF...>` UTF-16BE labels are decoded before persistence; valid semantic labels are not silently truncated. Scanned/image-only pages index successfully with no native text; M1-08 does not run OCR, vision, or AI. Optional DrawingSheet candidates are created only when conservative structured page-label or native-text evidence supports a sheet number/title. Page API responses omit full native text and all private storage metadata. Indexing preserves every document revision and does not advance the project beyond Documents Uploaded.

The production Documents UI polls queued/running jobs at five-second intervals. After source verification succeeds for an eligible PDF, a bounded 15-second `Preparing PDF indexing…` grace allows the automatically chained durable job to become visible before an explicit Index PDF action is offered. The browser never creates the automatic job. A fresh page load always refetches persisted processing state and page counts from Django.

## Structured AI analysis

M1-09 adds explicitly requested, versioned machine analysis for source-verified and indexed PDF revisions. Upload and indexing never trigger an AI call. Admin and Estimator / Operator members may start analysis, explicitly run it again after success, or retry a failed run from a numeric production project's AI Review tab; Viewer members may only read persisted history and results. Refreshing, polling, changing revisions, or selecting historical runs never initiates analysis.

Backend configuration is environment based:

```text
AI_PROVIDER=openai
AI_MODEL=gpt-5-mini
OPENAI_API_KEY=
AI_MAX_PAGES_PER_RUN=50
AI_MAX_NATIVE_TEXT_CHARS=30000
AI_RENDER_MAX_DIMENSION=2048
AI_TASK_MAX_ATTEMPTS=3
```

Keep `OPENAI_API_KEY` only in ignored local or production-secret configuration. The browser never receives it. Tests use a deterministic fake provider and make no network calls. Each explicit request creates an immutable `AnalysisRun`, one page task per indexed page, and a document-synthesis task. Text-heavy pages use indexed native text, drawing sheets use native text plus an exact temporary page render, and pages without native text use vision only. M1-09 adds no OCR.

For a local fake-provider operational test, set `AI_PROVIDER=fake`, `AI_PROVIDER_CLASS=apps.analysis.providers.FakeAnalysisProvider`, and `AI_FAKE_MODE=success` only in ignored `backend/.env`, then restart Django and Celery. The fake supports `success`, `timeout`, `rate_limit`, `unavailable`, `permanent_failure`, and `invalid_schema`; `AI_FAKE_INCLUDE_USAGE=false` tests missing usage metadata. Never configure the fake provider in production. Transient failures are durably re-queued with exponential backoff based on `AI_RETRY_BASE_SECONDS`; terminal failures are not retried.

Live-provider validation is a separately authorized operation. Do not place an API key in source control or chat, and do not switch a local validation environment from the fake provider without explicit approval because every Run or Run Again action may consume provider usage.

The normal Celery worker processes both document jobs and analysis runs:

```powershell
Set-Location backend
.venv\Scripts\celery.exe -A config worker --loglevel=INFO --pool=solo
```

Queued analysis intent remains in PostgreSQL. Operational recovery commands from `backend/` are:

```powershell
.venv\Scripts\python.exe manage.py dispatch_queued_analysis_runs
.venv\Scripts\python.exe manage.py recover_stale_analysis_runs
```

Analysis APIs are organization/project/document/revision scoped. Responses expose validated machine output, versions, safe usage metadata, and controlled failures, but no provider key, private storage location, full provider response, or chain-of-thought. Results are explicitly labelled **Machine generated — not yet human reviewed**. M1-10 owns formal findings, provenance records, conflicts, and human decisions.

## Finding materialization and human review

M1-10 adds a zero-AI-cost review layer over successful persisted analysis runs. Admin and Estimator / Operator members explicitly prepare one run for review; Viewer members are read-only. Repeating preparation is idempotent and never changes the original machine result.

```text
POST /api/v1/organizations/{slug}/projects/{project_id}/analysis-runs/{run_id}/findings/materialize/
GET  /api/v1/organizations/{slug}/projects/{project_id}/analysis-runs/{run_id}/findings/
GET  /api/v1/organizations/{slug}/projects/{project_id}/findings/{finding_id}/
GET  /api/v1/organizations/{slug}/projects/{project_id}/findings/{finding_id}/sources/
GET/POST /api/v1/organizations/{slug}/projects/{project_id}/findings/{finding_id}/reviews/
GET  /api/v1/organizations/{slug}/projects/{project_id}/conflicts/
POST /api/v1/organizations/{slug}/projects/{project_id}/conflicts/{conflict_id}/resolve/
```

Machine values and provenance remain immutable. Accept, Edited / Accepted, Reject, and Needs Clarification create append-only review records. An exact consecutive duplicate of the trimmed decision/value/note payload returns the current review without adding a review or audit row; meaningful changes append normally. Deterministic conflicts preserve every participant; resolution or dismissal creates a superseding conflict version. Preparing the first run may advance `ai_analysis` to `human_scope_review`, but reviewed findings remain **not yet approved project intelligence** until an exact M1-11 snapshot is explicitly approved.

## Intelligence snapshots and approval

M1-11 creates immutable project-level intelligence from explicitly selected, successful, materialized AnalysisRuns. A request supplies run IDs only: the server includes the complete finding set for each run and accepts at most one run per current DocumentRevision. Accepted values enter the intelligence payload, edited/accepted values use the human-reviewed value, rejected findings remain frozen in history but are excluded from intelligence, and unreviewed or needs-clarification findings block creation. Missing provenance, open conflicts, historical revisions, and contradictory selected review sets also block readiness. No AI/provider call occurs.

```text
GET/POST /api/v1/organizations/{slug}/projects/{project_id}/intelligence-readiness/
GET/POST /api/v1/organizations/{slug}/projects/{project_id}/intelligence-snapshots/
GET      /api/v1/organizations/{slug}/projects/{project_id}/intelligence-snapshots/{snapshot_id}/
GET/POST /api/v1/organizations/{slug}/projects/{project_id}/intelligence-snapshots/{snapshot_id}/approval/
```

Snapshot manifests and normalized relational rows freeze the exact runs, revisions, findings, effective reviews, reviewed values, and bounded page/sheet/task provenance. A canonical, key-sorted compact JSON representation is hashed with SHA-256; equivalent source/review state is idempotent, while a meaningful change creates the next project snapshot version. Approval targets one exact snapshot, is explicit and immutable, and rechecks the current review/source fingerprint so stale drafts cannot be approved. Admin and Estimator / Operator members may create and self-approve; Viewer members are read-only. Approval leaves the project in `human_scope_review`; Milestone 2 owns trade-package readiness.

## Project audit history

Numeric production projects expose a read-only Activity tab backed by server-side `AuditEvent` records:

```text
GET /api/v1/organizations/{slug}/projects/{project_id}/audit-events/
```

All active organization roles may read the project-scoped feed; mutation methods are unavailable. The response includes the event identity, action, safe target reference, actor display name, and UTC timestamp. Raw audit metadata is intentionally excluded from this general project feed because it may contain detailed before/after business values. Audit retention, export, and privileged detail access remain deployment-policy decisions.

## Local ports

| Service | Port | Purpose |
|---|---:|---|
| Next.js | 3000 | Existing frontend demo |
| Django | 8000 | Versioned backend API |
| PostgreSQL | 5432 | Production-system-of-record development database |
| Redis | 6379 | Celery broker and result backend |
| MinIO API | 9000 | Local S3-compatible endpoint |
| MinIO Console | 9001 | Local storage administration |

## Validation and production build

```bash
npm run typecheck
npm run lint
npm run build
```

Backend validation from `backend/`:

```bash
python -m ruff format --check .
python -m ruff check .
python -m pytest
python manage.py check
python manage.py makemigrations --check --dry-run
```

Production settings do not read `backend/.env` and require explicit environment values. The final production hosting and authentication topology remain unresolved architecture decisions.

## Stop or reset local infrastructure

Stop containers while retaining local data:

```bash
docker compose --env-file backend/.env -f infra/compose.yaml down
```

Delete the local PostgreSQL, Redis, and MinIO volumes and recreate from scratch:

```bash
docker compose --env-file backend/.env -f infra/compose.yaml down -v
```

The reset command permanently removes local infrastructure data. It does not remove repository files.

## Important demo disclosure

The repository preserves the approved fictional frontend demonstration for future procurement, bid, proposal, award, and downstream workflow screens. Numeric project routes are the Milestone 1 production path and use Django/PostgreSQL state for project intake, documents, processing, PDF indexing, structured analysis, human review, intelligence snapshots, approval, and project activity.

Fake-provider outputs are deterministic validation artifacts and are never presented as approved project facts until the human-review and snapshot-approval gates are completed. Milestone 1 does not include OCR, live-provider acceptance, production cloud deployment, trade packages, subcontractor discovery, outreach, bid leveling, proposals, awards, or project-management synchronization.
