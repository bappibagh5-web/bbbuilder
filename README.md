# BB Builders AI Bid Automation System

This repository contains the approved Next.js frontend demonstration and the production backend foundation for the BB Builders AI Bid Automation System.

Milestone 1 implementation is intentionally incremental. The existing demo remains the UX baseline and still uses deterministic fixture data until later Milestone 1 tasks connect individual workflows to production APIs.

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

No business or document-processing tasks exist yet. The worker only verifies that Django loads the Celery application and can connect to Redis.

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

M1-03 adds persistent organization-scoped projects and project contacts. The existing Next.js project screens remain fixture-driven until M1-04.

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

All project data, subcontractors, bids, AI findings, communication activity, pricing, and client activity are fictional demonstration data.

The current frontend screens still use fictional deterministic data and temporary React state. M1-01 adds only the backend and local-infrastructure foundation: it does not add project CRUD, uploads, document processing, AI calls, authentication screens, procurement, bid, or proposal functionality.
