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
- M1-UX-01 — Non-Technical Document Review UX: complete
- M1-UX-02A — Document Archive / Restore: complete; automated validation and client manual acceptance passed September 5, 2026
- M1-UX-03 — Smart Human Review: complete; deterministic exception triage passed automated and client manual validation September 6, 2026
- Milestone 2: complete, including accepted Scopes/Contractors lazy-loading performance polish; M3-01 is next and not started
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

### Document archive policy

Document archive controls active workflow membership; it never deletes or rewrites files, revisions, processing, analysis, findings, reviews, provenance, snapshots, approvals, or audit history. Archived documents are excluded from normal Document Review selection and new project-information source selection. When no active documents remain, the document-specific area shows an empty state without an AI action while project-wide historical versions and approvals remain readable. An archived source blocks approval of an unapproved snapshot, but archive state alone does not make the frozen snapshot stale or change its fingerprint. Already approved historical versions remain approved and readable. Restoring a source may recover draft approval eligibility when its meaningful frozen source/review state is otherwise current.

### M2A-01 trade scope builder

M2A-01 deterministically converts approved Project Information only into trade bid packages; it never calls an AI provider and never consumes unapproved findings. The controlled taxonomy aggregates the real JD Sports Version 1 into HVAC / Mechanical, Plumbing, Fire Protection / Sprinkler, and General Requirements. One approved finding may source more than one package only when its text explicitly applies to multiple trades. Package versions are immutable and append-only: generation creates Draft V1, Edit creates a new Draft version, and Mark Ready creates an explicit Ready version. Repeated generation and repeated Ready actions are idempotent. Untouched legacy category-generated drafts may be superseded during explicit regeneration, while human-edited packages are preserved. All four real JD Sports packages were manually validated Ready.

### M2B-01 contractor discovery foundation

M2B-01 adds organization-scoped Company, Contact, and TradeCapability records plus project/scope candidate shortlists. Discovery is available only for the current Ready scope-package version, searches the internal network first, and invokes a configured provider only after an explicit user action. Provider access is abstracted behind deterministic fake and inactive Google Places implementations. Deduplication uses external provider ID, website domain, normalized phone, then normalized name plus city; ambiguous matches are preserved rather than silently merged. The fake provider and shortlist workflow were manually validated. Google Places is not active, no provider key is required, and outreach/M3 has not started.

### M2B-02 Google Places contractor discovery

M2B-02 activates backend-only Google Places API (New) Text Search behind the existing explicit Ready-scope discovery action. It uses controlled trade query expansion, project city/province/country, optional user keywords, a minimal response field mask, safe provider error mapping, internal-first results, and the established deterministic dedupe order. The first authorized live HVAC search for the JD Sports project returned 14 candidates. Historical fake-provider records are preserved for audit and testing but filtered from production-facing Google candidate lists; internal and real Google companies remain visible. The key exists only in ignored backend environment configuration. No automatic searches, OpenAI calls, outreach, or M3 behavior were added.

### M2B-03 deterministic contractor ranking

M2B-03 ranks every visible scope-bound candidate without a provider or AI call. The stable additive score uses exact trade capability (30), project-city match (20), internal BB network status (18), website (5), phone (5), Google rating tiers (up to 12), review-count tiers (up to 10), and existing shortlist status (5), capped at 100. Missing ratings or review counts add nothing and are never interpreted negatively. Best Match is the default, with Internal First, Rating, Review Count, and Company Name alternatives; lower-ranked candidates remain visible. The UI presents `X/100`, deterministic Excellent/Good/Possible fit bands, and an expandable explanation containing every actual contributing signal. Real JD Sports HVAC validation showed 14 Google candidates with Best Match scores and confirmed D.Peppard Mechanical could be added through **Add to Shortlist**, after which its state displayed **Shortlisted ✓**. The unimplemented future-outreach button was removed. Ranking is guidance only—not AI scoring, approval, or outreach.

### M2B-04 through M2B-06 contractor and contact readiness

Trade Coverage now summarizes each Ready JD Sports scope against a configurable shortlist target of three and supports shortlisted-only filtering plus explicit removal from the shortlist. Contractor profiles preserve Google/internal company identity while keeping human-entered contacts separate. Contact readiness requires an active primary contact with an email or phone; Admin and Estimator/Operator manage contacts and Viewer remains read-only.

For Google-discovered companies, **Find Contact Details** performs an explicit, backend-only, bounded lookup starting at the stored public website and following only a few same-site contact/team/about links. Suggestions show their public source and pre-fill the form, but a human must confirm before saving. Duplicate email or normalized-phone submissions are idempotent. Manual entry remains available and no-result behavior is explicit. Reliance Heating produced no suggestion during local validation because its site returned no usable public HTML to the limited client; zero contacts were created. No outreach/M3 functionality exists.

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

Milestone 1 acceptance used the deterministic fake provider. A separately authorized post-milestone smoke test later completed successfully as OpenAI Run 10 against the eight-page JD Sports Intercity mechanical IFC drawing set using `gpt-5-mini`. Never infer the effective provider from this document: inspect environment configuration without exposing secrets, and require explicit authorization before every paid run.

## M1-12 boundary

M1-12 should validate intake/upload/revisions, deterministic processing/indexing, structured analysis, provenance, human review, immutable intelligence snapshot/approval, workflow status, failure states, production UI/error messaging, and final Milestone 1 documentation against genuine BB Builders tender material.

M1-12 does not include scope/trade-package generation, trade taxonomy, subcontractor discovery, RFQ/outreach, bid workflows, proposal generation, award workflow, or PM sync. Those belong to later milestones.

The M1-12 implementation adds a safe read-only project Activity feed because persisted `AuditEvent` history previously had no production API/UI path. It also adds `docs/MILESTONE_1_ACCEPTANCE.md`, reconciles milestone documentation, and records the remaining production/UAT prerequisites. No new domain workflow, migration, provider call, or Milestone 2 feature was introduced.

## Business context and scope guard

BB Builders is a Canadian commercial general contractor with substantial retail work plus restaurant and office work. Historical evidence includes heterogeneous tender/RFP packages, architectural/MEP/structural drawings, landlord and responsibility schedules, subtrade quotes, trade lists, estimate/proposal revisions, schedules, and submittals. Revisions, responsibility splits, quote qualifications, and human judgment matter. Consult `PROJECT_CONTEXT.md` and `REAL_WORKFLOW.md` for canonical context.

The approved contract is 200 hours / $5,000; commercial totals are canonical in `ROADMAP.md`. Do not silently add full invoicing, change-order or RFI management, complete submittal/closeout workflows, accounting, scheduling, or ERP/project-management functionality.

## Next exact action

Milestones 1 and 2 are complete. M2A-01, M2B-01 through M2B-06, and the final summary-first Scopes/Contractors UI were manually accepted. Project 3 Project Information V4 retains 27 current trade packages and 659 detailed ScopeItems, with 106 project-wide requirements separate. Scopes returns a 4-query, approximately 14.1 KB summary (five-run local average 0.96 seconds versus approximately 19.46 seconds, at least 8,997 queries, and 2.36 MB before), starts all trade rows collapsed, and lazily caches exact package details. Contractor Discovery initially loads only its 5-query coverage response (16 ms average, 738 bytes), then lazily caches candidates per expanded Ready trade; HVAC's 31 active production-facing candidates averaged 29 ms and 23.2 KB. Profiles, enrichment, searches, mutations, and history remain user-triggered. The exact next task is **M3-01 — Invitation / Outreach Domain Model**, which will model invitation campaigns/batches, recipient status, and traceable immutable message history. Do not begin it without explicit approval. No provider search or outreach is part of page load, and no outreach currently exists.

Smart Human Review now derives machine handling from persisted evidence without another provider call. A finding is AI handled only when it is explicit or strongly supported, every provider evidence reference remains strictly and completely represented by exact revision/page provenance, it is not an open question, it has no open conflict, and no human review supersedes it. Human-reviewed decisions remain append-only and distinct. Snapshot entry decision `machine_handled` has no `FindingReview`; migration `analysis.0004` makes that honest representation possible. Run 10's current read-only split is 23 AI handled / 7 needing attention / 0 conflicting. Final project-information approval is still an authorized human action.

Staging/UAT must still validate the deployed environment, secrets, network behavior, latency, cost, and monitoring. Known performance work—bounded parallel page analysis, safe reuse/resume, and live x-of-N progress—has not been implemented and must not be assumed.

M1-UX-01 was manually accepted on numeric production Project 2. The UI presents `Uploaded → Prepared → AI Review → Your Review → Approved`, familiar finding categories and decisions, understandable provenance, clear selected-document versus project-wide approval scope, concise collapsed project information versions, and Viewer read-only guidance. Technical run/provider/token/fingerprint information remains available only under collapsed Advanced details. No backend model/API semantics or commercial roadmap totals changed.

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
