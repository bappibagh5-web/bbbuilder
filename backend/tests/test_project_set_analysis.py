import hashlib

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analysis.models import AnalysisRun, AnalysisTaskRun
from apps.analysis.project_reconciliation import reconcile_project_set_page_results
from apps.analysis.prompts import ANALYSIS_VERSION, PAGE_PROMPT_VERSION
from apps.analysis.schemas import PAGE_SCHEMA_VERSION
from apps.analysis.services import (
    _filter_synthesis_evidence,
    _finish_run,
    materialize_reconciled_project_set_run,
    request_project_set_analysis_run,
)
from apps.documents.models import (
    Document,
    DocumentPage,
    DocumentRevision,
    FileAsset,
    ProjectDocumentSelection,
    ProjectFile,
)
from apps.organizations.models import Membership
from apps.projects.models import Project

pytestmark = pytest.mark.django_db


def add_source(project, user, *, title, discipline, page_count=2):
    content = title.encode()
    asset = FileAsset.objects.create(
        organization=project.organization,
        bucket="test",
        storage_key=f"project-set/{title}.pdf",
        original_filename=f"{title}_IFC.pdf",
        declared_mime_type="application/pdf",
        detected_mime_type="application/pdf",
        byte_size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        created_by=user,
    )
    project_file = ProjectFile.objects.create(project=project, file_asset=asset, created_by=user)
    document = Document.objects.create(
        project=project,
        title=title,
        category=Document.Category.DRAWINGS,
        discipline=discipline,
        created_by=user,
    )
    revision = DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        revision_label="IFC",
        source_filename=asset.original_filename,
        created_by=user,
    )
    Document.objects.filter(pk=document.pk).update(current_revision=revision)
    document.refresh_from_db()
    pages = [
        DocumentPage.objects.create(
            document_revision=revision,
            page_number=number,
            page_label=str(number),
            width_points=612,
            height_points=792,
            native_text=f"{discipline} coordinated work page {number}",
            native_text_char_count=len(f"{discipline} coordinated work page {number}"),
            has_native_text=True,
            parser_name="test",
            parser_version="1",
        )
        for number in range(1, page_count + 1)
    ]
    ProjectDocumentSelection.objects.create(
        project=project,
        document=document,
        selected_revision=revision,
        is_included=True,
        updated_by=user,
    )
    return document, revision, pages


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-SET-AI-001",
        name="Coordinated Review",
        project_timezone="America/Vancouver",
        status=Project.Status.HUMAN_SCOPE_REVIEW,
    )


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_project_set_run_freezes_all_sources_and_reuses_compatible_pages(project, user):
    _, mechanical_revision, mechanical_pages = add_source(
        project, user, title="Mechanical", discipline=Document.Discipline.MECHANICAL
    )
    _, electrical_revision, electrical_pages = add_source(
        project, user, title="Electrical", discipline=Document.Discipline.ELECTRICAL
    )
    old_run = AnalysisRun.objects.create(
        document_revision=mechanical_revision,
        requested_by=user,
        provider="fake",
        model="fake-v1",
        prompt_version="old",
        schema_version="old",
        analysis_version=ANALYSIS_VERSION,
        input_manifest={"document_revision_id": mechanical_revision.pk},
        status=AnalysisRun.Status.SUCCEEDED,
    )
    reusable = AnalysisTaskRun.objects.create(
        analysis_run=old_run,
        document_page=mechanical_pages[0],
        task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
        input_mode=AnalysisTaskRun.InputMode.NATIVE_TEXT,
        status=AnalysisTaskRun.Status.SUCCEEDED,
        provider="fake",
        model="fake-v1",
        prompt_version=PAGE_PROMPT_VERSION,
        schema_version=PAGE_SCHEMA_VERSION,
        input_metadata={"document_page_id": mechanical_pages[0].pk},
        structured_result={"reused": True},
        finished_at=timezone.now(),
    )

    run = request_project_set_analysis_run(project=project, requested_by=user)

    assert run.run_kind == AnalysisRun.RunKind.PROJECT_SET
    assert run.project_context_id == project.pk
    assert set(run.input_manifest["document_revision_ids"]) == {
        mechanical_revision.pk,
        electrical_revision.pk,
    }
    assert set(run.input_manifest["page_ids"]) == {
        *(page.pk for page in mechanical_pages),
        *(page.pk for page in electrical_pages),
    }
    assert run.input_manifest["page_count"] == 4
    assert "HVAC / Mechanical" in run.input_manifest["trade_taxonomy"]
    assert "Owner Supplied" in run.input_manifest["responsibility_labels"]
    tasks = run.task_runs.filter(task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS)
    assert tasks.count() == 4
    assert tasks.get(document_page=mechanical_pages[0]).reused_from_id == reusable.pk
    assert tasks.get(document_page=electrical_pages[0]).reused_from_id is None


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_project_set_synthesis_accepts_exact_cross_document_provenance(project, user):
    _, _, mechanical_pages = add_source(
        project, user, title="Mechanical", discipline=Document.Discipline.MECHANICAL, page_count=1
    )
    _, electrical_revision, electrical_pages = add_source(
        project, user, title="Electrical", discipline=Document.Discipline.ELECTRICAL, page_count=1
    )
    run = request_project_set_analysis_run(project=project, requested_by=user)
    for task in run.task_runs.filter(task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS):
        task.status = AnalysisTaskRun.Status.SUCCEEDED
        task.save(update_fields=("status", "updated_at"))
    synthesis = run.task_runs.get(task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS)
    evidence = {
        "document_page_id": electrical_pages[0].pk,
        "page_number": 1,
        "drawing_sheet_id": None,
        "sheet_number": "",
        "evidence_excerpt": "electrical coordinated work page 1",
        "visual_evidence_description": "",
    }
    result, counts = _filter_synthesis_evidence(
        synthesis,
        {
            "candidates": [
                {
                    "category": "scope_trade",
                    "subject": "Electrical coordination",
                    "value": "Coordinate electrical connection.",
                    "support": "explicit",
                    "evidence": [evidence],
                }
            ]
        },
    )
    assert result["candidates"][0]["evidence"] == [evidence]
    assert counts["accepted"] == 1
    cross_document_task = run.task_runs.get(document_page=electrical_pages[0])
    cross_document_task.full_clean()
    assert electrical_revision.pk in run.input_manifest["document_revision_ids"]
    assert mechanical_pages[0].pk in run.input_manifest["page_ids"]


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_project_set_reconciliation_preserves_broad_grounded_coverage(project, user):
    _, _, mechanical_pages = add_source(
        project, user, title="Mechanical", discipline=Document.Discipline.MECHANICAL, page_count=1
    )
    _, _, electrical_pages = add_source(
        project, user, title="Electrical", discipline=Document.Discipline.ELECTRICAL, page_count=1
    )
    run = request_project_set_analysis_run(project=project, requested_by=user)
    candidates = (
        (mechanical_pages[0], "Mechanical ductwork", "Supply and install ductwork."),
        (electrical_pages[0], "Electrical lighting", "Supply and install lighting."),
    )
    for page, subject, value in candidates:
        task = run.task_runs.get(document_page=page)
        task.status = AnalysisTaskRun.Status.SUCCEEDED
        task.structured_result = {
            "candidates": [
                {
                    "category": "scope_trade",
                    "subject": subject,
                    "value": value,
                    "support": "explicit",
                    "evidence": [
                        {
                            "document_page_id": page.pk,
                            "page_number": page.page_number,
                            "drawing_sheet_id": None,
                            "sheet_number": "",
                            "evidence_excerpt": page.native_text,
                            "visual_evidence_description": "",
                        }
                    ],
                }
            ]
        }
        task.save(update_fields=("status", "structured_result", "updated_at"))

    result = reconcile_project_set_page_results(run)

    assert result["consolidated_finding_count"] == 2
    assert result["source_candidate_count"] == 2
    assert result["provenance_reference_count"] == 2
    assert result["coverage"]["trades"] == {"Electrical": 1, "HVAC / Mechanical": 1}
    assert set(result["coverage"]["documents"]) == {
        mechanical_pages[0].document_revision.document_id,
        electrical_pages[0].document_revision.document_id,
    }


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_reconciled_successor_is_append_only_provider_free_and_idempotent(project, user):
    Membership.objects.create(
        organization=project.organization,
        user=user,
        role=Membership.Role.ESTIMATOR_OPERATOR,
        is_active=True,
    )
    _, _, mechanical_pages = add_source(
        project, user, title="Mechanical", discipline=Document.Discipline.MECHANICAL, page_count=1
    )
    _, _, electrical_pages = add_source(
        project, user, title="Electrical", discipline=Document.Discipline.ELECTRICAL, page_count=1
    )
    source = request_project_set_analysis_run(project=project, requested_by=user)
    for page, subject, value in (
        (mechanical_pages[0], "Mechanical ductwork", "Supply and install ductwork."),
        (electrical_pages[0], "Electrical lighting", "Supply and install lighting."),
    ):
        task = source.task_runs.get(document_page=page)
        task.status = AnalysisTaskRun.Status.SUCCEEDED
        task.structured_result = {
            "candidates": [
                {
                    "category": "scope_trade",
                    "subject": subject,
                    "value": value,
                    "support": "explicit",
                    "evidence": [
                        {
                            "document_page_id": page.pk,
                            "page_number": page.page_number,
                            "drawing_sheet_id": None,
                            "sheet_number": "",
                            "evidence_excerpt": page.native_text,
                            "visual_evidence_description": "",
                        }
                    ],
                }
            ]
        }
        task.save(update_fields=("status", "structured_result", "updated_at"))
    source_synthesis = source.task_runs.get(task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS)
    source_synthesis.status = AnalysisTaskRun.Status.SUCCEEDED
    source_synthesis.structured_result = {
        "document_type_candidate": "Project set",
        "document_summary": "Original provider synthesis.",
        "candidates": [],
        "unresolved_questions": [],
    }
    source_synthesis.save(update_fields=("status", "structured_result", "updated_at"))
    source.status = AnalysisRun.Status.SUCCEEDED
    source.result_summary = source_synthesis.structured_result
    source.finished_at = timezone.now()
    source.save(update_fields=("status", "result_summary", "finished_at", "updated_at"))
    original_result = source.result_summary.copy()

    successor, findings, reconciliation, created = materialize_reconciled_project_set_run(
        source_run=source, actor=user
    )
    repeated, repeated_findings, _, repeated_created = materialize_reconciled_project_set_run(
        source_run=source, actor=user
    )

    source.refresh_from_db()
    assert source.result_summary == original_result
    assert created is True
    assert repeated_created is False
    assert repeated.pk == successor.pk
    assert successor.predecessor_id == source.pk
    assert successor.provider == "deterministic_reconciliation"
    assert successor.usage_metadata["provider_requests"] == 0
    assert reconciliation["consolidated_finding_count"] == 2
    assert findings.count() == repeated_findings.count() == 2
    assert (
        successor.task_runs.filter(
            task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
            reused_from__isnull=False,
        ).count()
        == 2
    )
    assert successor.task_runs.count() == 3
    assert sum(finding.sources.count() for finding in findings) == 2
    state_path = reverse(
        "project-review-state",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    client = APIClient()
    client.force_authenticate(user)
    state = client.get(state_path)
    assert state.status_code == 200
    assert state.data["current_run"]["id"] == successor.pk
    assert state.data["counts"]["total"] == 2
    assert state.data["materialized"] is True
    assert "findings" not in state.data
    finding_path = reverse(
        "project-review-finding-list",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    page = client.get(finding_path, {"page_size": 1})
    assert page.status_code == 200
    assert page.data["count"] == 2
    assert page.data["page_size"] == 1
    assert len(page.data["results"]) == 1


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_project_set_reconciliation_accounts_for_duplicate_invalid_and_supporting_only(
    project, user
):
    document, _, pages = add_source(
        project,
        user,
        title="Electrical product data",
        discipline=Document.Discipline.ELECTRICAL,
        page_count=1,
    )
    document.category = Document.Category.SPECIFICATIONS
    document.save(update_fields=("category", "updated_at"))
    run = request_project_set_analysis_run(project=project, requested_by=user)
    page = pages[0]
    evidence = {
        "document_page_id": page.pk,
        "page_number": 1,
        "drawing_sheet_id": None,
        "sheet_number": "",
        "evidence_excerpt": page.native_text,
        "visual_evidence_description": "",
    }
    scoped = {
        "category": "scope_trade",
        "subject": "Electrical work",
        "value": "Provide electrical connection.",
        "support": "explicit",
        "evidence": [evidence],
    }
    supporting = {
        "category": "project_fact",
        "subject": "Catalog colour",
        "value": "White finish.",
        "support": "explicit",
        "evidence": [evidence],
    }
    invalid = {**scoped, "subject": "Invalid", "evidence": [{**evidence, "page_number": 99}]}
    task = run.task_runs.get(document_page=page)
    task.status = AnalysisTaskRun.Status.SUCCEEDED
    task.structured_result = {"candidates": [scoped, scoped, supporting, invalid]}
    task.save(update_fields=("status", "structured_result", "updated_at"))

    result = reconcile_project_set_page_results(run)

    assert result["source_candidate_count"] == 4
    assert result["consolidated_finding_count"] == 1
    assert result["dispositions"] == {
        "duplicate": 1,
        "supporting_only": 1,
        "invalid": 1,
        "consolidated": 0,
    }
    assert sorted(item["reason"] for item in result["omissions"]) == [
        "duplicate",
        "invalid",
        "supporting_only",
    ]
    assert result["candidates"][0]["evidence"] == [evidence]


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_project_set_reconciliation_separates_obligations_and_omits_contact_metadata(project, user):
    _, _, pages = add_source(
        project,
        user,
        title="Electrical quote and product requirements",
        discipline=Document.Discipline.ELECTRICAL,
        page_count=1,
    )
    run = request_project_set_analysis_run(project=project, requested_by=user)
    page = pages[0]
    evidence = {
        "document_page_id": page.pk,
        "page_number": 1,
        "drawing_sheet_id": None,
        "sheet_number": "",
        "evidence_excerpt": page.native_text,
        "visual_evidence_description": "",
    }
    candidates = [
        {
            "category": "submittal_closeout",
            "subject": "Luminaire warranty",
            "value": "Provide a five-year warranty.",
            "support": "explicit",
            "evidence": [evidence],
        },
        {
            "category": "submittal_closeout",
            "subject": "Luminaire rating",
            "value": "Luminaire is damp-location rated.",
            "support": "explicit",
            "evidence": [evidence],
        },
        {
            "category": "commercial",
            "subject": "Payment terms",
            "value": "Payment is Net 30.",
            "support": "explicit",
            "evidence": [evidence],
        },
        {
            "category": "commercial",
            "subject": "Manufacturer contact",
            "value": "Contact design@example.invalid by email.",
            "support": "explicit",
            "evidence": [evidence],
        },
    ]
    task = run.task_runs.get(document_page=page)
    task.status = AnalysisTaskRun.Status.SUCCEEDED
    task.structured_result = {"candidates": candidates}
    task.save(update_fields=("status", "structured_result", "updated_at"))

    result = reconcile_project_set_page_results(run)

    assert result["consolidated_finding_count"] == 3
    assert result["dispositions"]["supporting_only"] == 1
    assert {candidate["subject"] for candidate in result["candidates"]} == {
        "Luminaire warranty",
        "Luminaire rating",
        "Payment terms",
    }


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_project_set_reconciliation_triages_dates_and_responsibilities(project, user):
    _, _, pages = add_source(
        project,
        user,
        title="Project requirements",
        discipline=Document.Discipline.ARCHITECTURAL,
        page_count=1,
    )
    run = request_project_set_analysis_run(project=project, requested_by=user)
    page = pages[0]
    evidence = {
        "document_page_id": page.pk,
        "page_number": 1,
        "drawing_sheet_id": None,
        "sheet_number": "",
        "evidence_excerpt": page.native_text,
        "visual_evidence_description": "",
    }
    candidates = [
        {
            "category": "date_deadline",
            "subject": "IFC issue date",
            "value": "Issued for construction on 2026-04-10.",
            "support": "explicit",
            "evidence": [evidence],
        },
        {
            "category": "date_deadline",
            "subject": "Tender close",
            "value": "Bid deadline is 2026-05-01.",
            "support": "explicit",
            "evidence": [evidence],
        },
        {
            "category": "landlord_requirement",
            "subject": "Roof work",
            "value": "Landlord contractor shall complete all roof work.",
            "support": "explicit",
            "evidence": [evidence],
        },
        {
            "category": "responsibility",
            "subject": "Fixture supply",
            "value": "Fixture supplier is TBC.",
            "support": "explicit",
            "evidence": [evidence],
        },
    ]
    task = run.task_runs.get(document_page=page)
    task.status = AnalysisTaskRun.Status.SUCCEEDED
    task.structured_result = {"candidates": candidates}
    task.save(update_fields=("status", "structured_result", "updated_at"))

    result = reconcile_project_set_page_results(run)
    by_subject = {candidate["subject"]: candidate for candidate in result["candidates"]}

    assert result["dispositions"]["supporting_only"] == 1
    assert "IFC issue date" not in by_subject
    assert by_subject["Tender close"]["support"] == "explicit"
    assert by_subject["Roof work"]["support"] == "explicit"
    assert by_subject["Fixture supply"]["support"] == "uncertain"


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_project_set_reconciliation_uses_page_bound_visual_evidence_without_false_quote(
    project, user
):
    _, _, pages = add_source(
        project,
        user,
        title="Duct Interference",
        discipline=Document.Discipline.MECHANICAL,
        page_count=1,
    )
    run = request_project_set_analysis_run(project=project, requested_by=user)
    page = pages[0]
    task = run.task_runs.get(document_page=page)
    AnalysisTaskRun.objects.filter(pk=task.pk).update(
        input_mode=AnalysisTaskRun.InputMode.NATIVE_TEXT_VISION
    )
    task.refresh_from_db()
    task.status = AnalysisTaskRun.Status.SUCCEEDED
    task.structured_result = {
        "candidates": [
            {
                "category": "open_question",
                "subject": "Coordinate duct and structure",
                "value": "Confirm the field resolution.",
                "support": "uncertain",
                "evidence": [
                    {
                        "document_page_id": page.pk,
                        "page_number": 1,
                        "drawing_sheet_id": None,
                        "sheet_number": "",
                        "evidence_excerpt": "TEXT NOT PRESENT ON THIS IMAGE",
                        "visual_evidence_description": "Markup identifies the duct-column clash.",
                    }
                ],
            }
        ]
    }
    task.save(update_fields=("status", "structured_result", "updated_at"))

    result = reconcile_project_set_page_results(run)

    assert result["consolidated_finding_count"] == 1
    assert result["dispositions"]["invalid"] == 0
    evidence = result["candidates"][0]["evidence"][0]
    assert evidence["evidence_excerpt"] == ""
    assert evidence["visual_evidence_description"] == "Markup identifies the duct-column clash."


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_project_set_completion_records_taxonomy_and_coordination_coverage(project, user):
    add_source(
        project,
        user,
        title="Mechanical IFC",
        discipline=Document.Discipline.MECHANICAL,
        page_count=1,
    )
    run = request_project_set_analysis_run(project=project, requested_by=user)
    page_task = run.task_runs.get(task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS)
    page_task.status = AnalysisTaskRun.Status.SUCCEEDED
    page_task.save(update_fields=("status", "updated_at"))
    synthesis = run.task_runs.get(task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS)
    synthesis.status = AnalysisTaskRun.Status.SUCCEEDED
    synthesis.structured_result = {
        "candidates": [
            {
                "category": "scope_trade",
                "subject": "Mechanical ductwork",
                "value": "Supply and install coordinated ductwork.",
                "support": "explicit",
                "evidence": [],
            }
        ],
        "unresolved_questions": ["Confirm electrical connection responsibility."],
    }
    synthesis.save(update_fields=("status", "structured_result", "updated_at"))

    _finish_run(run)

    run.refresh_from_db()
    assert run.usage_metadata["coverage"] == {
        "represented_disciplines": [Document.Discipline.MECHANICAL],
        "coordination_questions": 1,
        "covered_trade_packages": ["HVAC / Mechanical"],
        "unmapped_candidate_count": 0,
        "scope_taxonomy_check": "complete",
    }


@override_settings(AI_AUTO_DISPATCH=False, AI_PROVIDER="fake", AI_MODEL="fake-v1")
def test_project_set_api_is_operator_write_viewer_read_only(project, user, membership):
    add_source(project, user, title="Mechanical", discipline=Document.Discipline.MECHANICAL)
    path = reverse(
        "project-set-analysis-run-list",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    client = APIClient()
    client.force_authenticate(user)
    assert client.get(path).status_code == 200
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    assert client.post(path, {}, format="json").status_code == 403
    membership.role = Membership.Role.ESTIMATOR_OPERATOR
    membership.save(update_fields=("role",))
    response = client.post(path, {}, format="json")
    assert response.status_code == 201
    assert response.data["run_kind"] == "project_set"
    assert response.data["progress"]["total"] == 2
