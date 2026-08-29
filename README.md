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

Copy the safe example file and replace its local placeholder passwords. Keep `backend/.env` untracked.

PowerShell:

```powershell
Copy-Item backend/.env.example backend/.env
```

POSIX shell:

```bash
cp backend/.env.example backend/.env
```

The same file supplies local Django configuration and Docker Compose service credentials. Ensure `DATABASE_URL`, the `POSTGRES_*` values, and the MinIO/S3 credentials agree.

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
backend/.venv/Scripts/python backend/manage.py runserver 127.0.0.1:8000
```

POSIX shell:

```bash
backend/.venv/bin/python backend/manage.py migrate
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

Open `http://localhost:3000`. The root route redirects to the dashboard. M1-01 does not replace the frontend fixtures or connect its screens to backend APIs.

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
