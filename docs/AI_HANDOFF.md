# BB Builders AI Continuity Handoff

This is an operational continuity and navigation brief for a new ChatGPT/Codex session or account. It is not an architectural source of truth and does not replace the permanent specifications.

## Source-of-truth hierarchy

Use sources in this order:

1. Current Git working tree, `git status`, and committed Git history
2. `docs/CURRENT_STATUS.md`
3. `docs/DECISIONS.md`
4. `docs/ROADMAP.md`
5. `docs/DATA_MODEL.md`
6. `docs/BUSINESS_RULES.md`
7. Task- and milestone-specific permanent specifications
8. `docs/AI_HANDOFF.md`
9. Prior ChatGPT/Codex conversations as supplemental history only
10. Model or chat memory last

If this handoff conflicts with Git or canonical permanent documentation, stop and identify the conflict. Never allow a stale handoff or remembered chat to override committed repository state.

## `Sync BB Builders`

When the user says **Sync BB Builders**, perform a read-only recovery before proposing or making changes:

1. Inspect `git status`, current branch and HEAD, `origin/master`, ahead/behind divergence, recent history, untracked files, and any active merge, rebase, cherry-pick, or revert.
2. Read `README.md`, `PROJECT_CONTEXT.md`, `ROADMAP.md`, `REAL_WORKFLOW.md`, `DATA_MODEL.md`, relevant milestone specifications, `AI_DOCUMENT_PIPELINE.md` where relevant, `BUSINESS_RULES.md`, `DECISIONS.md`, `CURRENT_STATUS.md`, and this file.
3. Report the current branch/HEAD/synchronization, latest completed and pushed task, active task and stage, important recent decisions, unresolved blockers, current manual-validation position, and next exact safe action.
4. Modify nothing until continuity is established.
5. If Git and documentation conflict, stop and report the conflict.
6. If uncommitted work exists, audit it before proposing changes.

## Checkpoint at creation

- Repository: `D:\Codex Project\BB Builders`
- Remote: `https://github.com/bappibagh5-web/bbbuilder.git`
- Branch: `master`
- Latest pushed HEAD: `6016e4ab7476b89295cb873676e247b48530405a`
- Latest completed and pushed task: M1-11 — Intelligence Snapshot, Approval & Audit
- M1-01 through M1-11: complete and pushed
- M1-12 — Real BB Builders Project Validation & Milestone Polish: complete
- Milestone 1: complete
- Milestone 2: not started
- Working tree: clean
- Ahead/behind: `0/0`

`CURRENT_STATUS.md` overrides these values when the project advances.

## Current delivery position

M1-12 is the final Milestone 1 task. It must validate the complete production journey with genuine BB Builders historical tender material and perform milestone-level polish. It must not begin Milestone 2 scope or trade-package generation.

### Recent M1-11 decisions

- A `ProjectIntelligenceSnapshot` is project-level and may explicitly select successful runs from multiple current document revisions in the same project.
- Only one AnalysisRun per DocumentRevision may participate, and each selected run contributes its complete materialized finding set; findings cannot be cherry-picked.
- A new snapshot can use only each document's current revision.
- Accepted and edited/accepted findings may enter approved intelligence. Rejected findings remain frozen history but are excluded.
- Unreviewed or Needs Clarification findings, missing provenance, and open conflicts block readiness.
- Exact findings, effective reviews, sources, revisions, pages/sheets, task provenance, decisions, and values are frozen.
- The fingerprint is deterministic SHA-256 over canonical frozen state.
- Historical snapshots are immutable. Stale drafts cannot be approved, while prior approved snapshots remain historically approved.
- Approval targets an exact snapshot. Admin and Estimator/Operator may create and approve; Viewer is read-only; explicit self-approval is permitted.
- Approval leaves the project at `human_scope_review`. Milestone 2 owns trade-package creation and readiness.

See `DECISIONS.md`, `DATA_MODEL.md`, and `BUSINESS_RULES.md` for canonical detail.

## M1-11 manual validation

Project 2 (`BB-M1-04-TEST-002`) was validated with Document 4, **JD Sports Intercity Mechanical IFC Drawing Set**, current R1/revision 7, and Analysis Run #5 using the deterministic fake provider.

Validation proved that eight page tasks and one synthesis task succeeded; findings retained exact provenance; human review completed; Snapshot V1 was explicitly created and approved; approval survived refresh and logout/login; Viewer access was read-only; the project remained `human_scope_review`; and no trade-package transition occurred.

Approved Snapshot V1 fingerprint:

`bd285a985dd988ac016ffe598212e44621688d07e59078625408d84c2eb8caaa`

Append-only validation proved that later review changes did not rewrite V1, stale V2 approval was blocked without creating another approval, the documented blocked-stale audit was recorded, duplicate identical review submissions were idempotent, and accidental human review history remained preserved.

## Local validation context

- Project 2 status: `human_scope_review`
- Important documents: M1-06 Real Upload Test; AI Bid Automation Proposal CAD; JD Sports Intercity Mechanical IFC Drawing Set
- Existing local runs, revisions, reviews, snapshots, and approvals are intentional validation history. Do not reset or clean them for appearance.
- A local-only Viewer may exist as `m1-viewer-test@local.invalid`. Never store its password, and application code must not depend on it.

## Known traps

- Use `127.0.0.1` consistently: frontend `3000`, backend `8000`, PostgreSQL `5432`, Redis `6379`, MinIO API `9000`, MinIO Console `9001`.
- Windows Celery command from `backend`: `.venv\Scripts\celery.exe -A config worker --loglevel=INFO --pool=solo`.
- Restart a stale Celery worker after backend worker-code changes.
- Never reset the database without explicit approval.
- Never delete immutable historical revisions, findings, reviews, runs, snapshots, or approvals to clean validation data.
- Never make a historical DocumentRevision current merely to pass a test.
- Paid/live AI must never run implicitly. Inspect effective configuration without exposing secrets before AI validation.
- Keep `backend/.env` ignored. Never place API keys or passwords in chat, prompts, Git, or frontend code.
- Repository and Git state override remembered conversation context.

The local validation configuration has used the deterministic fake provider. No live OpenAI request or OpenAI API credit has been used during Milestone 1 validation. Do not assume the fake provider remains configured; a live-provider test requires explicit authorization.

## M1-12 boundary

M1-12 should validate intake/upload/revisions, deterministic processing/indexing, structured analysis, provenance, human review, immutable intelligence snapshot/approval, workflow status, failure states, production UI/error messaging, and final Milestone 1 documentation against genuine BB Builders tender material.

M1-12 does not include scope/trade-package generation, trade taxonomy, subcontractor discovery, RFQ/outreach, bid workflows, proposal generation, award workflow, or PM sync. Those belong to later milestones.

The M1-12 implementation adds a safe read-only project Activity feed because persisted `AuditEvent` history previously had no production API/UI path. It also adds `docs/MILESTONE_1_ACCEPTANCE.md`, reconciles milestone documentation, and records the remaining production/UAT prerequisites. No new domain workflow, migration, provider call, or Milestone 2 feature was introduced.

## Business context and scope guard

BB Builders is a Canadian commercial general contractor with substantial retail work plus restaurant and office work. Historical evidence includes heterogeneous tender/RFP packages, architectural/MEP/structural drawings, landlord and responsibility schedules, subtrade quotes, trade lists, estimate/proposal revisions, schedules, and submittals. Revisions, responsibility splits, quote qualifications, and human judgment matter. Consult `PROJECT_CONTEXT.md` and `REAL_WORKFLOW.md` for canonical context.

The approved contract is 200 hours / $5,000; commercial totals are canonical in `ROADMAP.md`. Do not silently add full invoicing, change-order or RFI management, complete submittal/closeout workflows, accounting, scheduling, or ERP/project-management functionality.

## Next exact action

Milestone 1 is complete. M2-01 is next but has not started. Before production acceptance, treat `LIVE_PROVIDER_SMOKE_RECOMMENDED` as a staging/UAT prerequisite; the live OpenAI provider has not been exercised and compatibility must not be claimed as proven.

## Maintenance

Refresh this brief at meaningful permanent checkpoints, especially after a task is pushed. Record the current HEAD, active task/stage, recent material decisions, unresolved blockers, and next exact action. Do not copy entire Codex prompts or duplicate permanent specifications. If this file becomes stale, Git and `CURRENT_STATUS.md` override it.

## Bootstrap prompt

```text
Sync BB Builders.

Repository:
D:\Codex Project\BB Builders

Reconstruct project state from Git and permanent docs before giving implementation instructions.

Read AI_HANDOFF.md, CURRENT_STATUS.md, DECISIONS.md, ROADMAP.md,
DATA_MODEL.md, BUSINESS_RULES.md, relevant specs, and recent Git history.

Repository state overrides remembered chat context.

First report:
- HEAD / branch / synchronization
- latest completed task
- current active task/stage
- important recent decisions
- unresolved blockers
- next exact safe action

Do not modify anything until continuity is established.
```
