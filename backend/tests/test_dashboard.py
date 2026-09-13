import hashlib

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analysis.models import (
    AnalysisRun,
    AnalysisTaskRun,
    ExtractedFinding,
    FindingReview,
    FindingSource,
    IntelligenceConflict,
    ProjectIntelligenceApproval,
    ProjectIntelligenceSnapshot,
)
from apps.documents.models import (
    Document,
    DocumentPage,
    DocumentRevision,
    FileAsset,
    ProjectDocumentSelection,
    ProjectFile,
)
from apps.documents.services import set_current_revision
from apps.organizations.models import Membership, Organization
from apps.projects.models import AuditEvent, Project

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def dashboard_url(organization):
    return reverse("dashboard-summary", kwargs={"organization_slug": organization.slug})


def activity_url(organization):
    return reverse("dashboard-activity", kwargs={"organization_slug": organization.slug})


def create_project(organization, user, number="BB-DASH-001", *, active=True):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number=number,
        name=f"Dashboard {number}",
        project_timezone="America/Vancouver",
        is_active=active,
    )


def create_reviewed_document(project, user, suffix, *, needs_attention=False):
    content = f"dashboard-{suffix}".encode()
    asset = FileAsset.objects.create(
        organization=project.organization,
        bucket="test",
        storage_key=f"dashboard/{project.pk}/{suffix}.pdf",
        original_filename=f"{suffix}.pdf",
        declared_mime_type="application/pdf",
        detected_mime_type="application/pdf",
        byte_size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        created_by=user,
    )
    project_file = ProjectFile.objects.create(project=project, file_asset=asset, created_by=user)
    document = Document.objects.create(project=project, title=suffix, created_by=user)
    revision = DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        revision_label="R1",
        source_filename=f"{suffix}.pdf",
        created_by=user,
    )
    set_current_revision(document=document, revision=revision, actor=user)
    run = AnalysisRun.objects.create(
        document_revision=revision,
        requested_by=user,
        status=AnalysisRun.Status.SUCCEEDED,
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        analysis_version="v1",
        input_manifest={"document_revision_id": revision.pk},
        finished_at=timezone.now(),
    )
    task = AnalysisTaskRun.objects.create(
        analysis_run=run,
        task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS,
        input_mode=AnalysisTaskRun.InputMode.STRUCTURED_PAGE_RESULTS,
        status=AnalysisTaskRun.Status.SUCCEEDED,
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        input_metadata={"test": True},
    )
    finding = ExtractedFinding.objects.create(
        analysis_run=run,
        analysis_task_run=task,
        document_revision=revision,
        source_candidate_key=f"candidate-{project.pk}-{suffix}",
        semantic_key=f"semantic-{project.pk}-{suffix}",
        category=(
            ExtractedFinding.Category.OPEN_QUESTION
            if needs_attention
            else ExtractedFinding.Category.PROJECT_FACT
        ),
        subject=suffix,
        machine_value="Value",
        normalized_machine_value="value",
        machine_support=ExtractedFinding.Support.EXPLICIT,
        schema_version="v1",
    )
    if not needs_attention:
        FindingReview.objects.create(
            finding=finding,
            reviewer=user,
            decision=FindingReview.Decision.ACCEPTED,
        )
    return document, run


def create_approval(project, user, version=1):
    snapshot = ProjectIntelligenceSnapshot.objects.create(
        project=project,
        version=version,
        fingerprint=f"{version:064d}",
        manifest={"test": True},
        summary_counts={"total": 1},
        created_by=user,
    )
    return ProjectIntelligenceApproval.objects.create(
        project=project,
        snapshot=snapshot,
        approver=user,
        readiness_result={"eligible": True},
    )


def create_project_set_review(project, user, documents):
    revisions = []
    for document in documents:
        document.refresh_from_db()
        revisions.append(document.current_revision)
        ProjectDocumentSelection.objects.create(
            project=project,
            document=document,
            selected_revision=document.current_revision,
            updated_by=user,
        )
    page = DocumentPage.objects.create(
        document_revision=revisions[1],
        page_number=1,
        width_points=612,
        height_points=792,
        native_text="Specified",
        native_text_char_count=9,
        has_native_text=True,
        parser_name="test",
        parser_version="1",
    )
    run = AnalysisRun.objects.create(
        document_revision=revisions[0],
        project_context=project,
        run_kind=AnalysisRun.RunKind.PROJECT_SET,
        requested_by=user,
        status=AnalysisRun.Status.SUCCEEDED,
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        analysis_version="v1",
        input_manifest={
            "document_revision_ids": [revision.pk for revision in revisions],
            "documents": [
                {"document_id": revision.document_id, "document_revision_id": revision.pk}
                for revision in revisions
            ],
            "page_count": 12,
            "page_ids": [page.pk],
        },
        finished_at=timezone.now(),
    )
    task = AnalysisTaskRun.objects.create(
        analysis_run=run,
        task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS,
        input_mode=AnalysisTaskRun.InputMode.STRUCTURED_PAGE_RESULTS,
        status=AnalysisTaskRun.Status.SUCCEEDED,
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        input_metadata={"test": True},
    )
    human = ExtractedFinding.objects.create(
        analysis_run=run,
        analysis_task_run=task,
        document_revision=revisions[0],
        source_candidate_key="project-set-human",
        semantic_key="project-set-human",
        category=ExtractedFinding.Category.PROJECT_FACT,
        subject="Human item",
        machine_value="Confirmed",
        normalized_machine_value="confirmed",
        machine_support=ExtractedFinding.Support.EXPLICIT,
        schema_version="v1",
    )
    FindingReview.objects.create(
        finding=human, reviewer=user, decision=FindingReview.Decision.ACCEPTED
    )
    ai = ExtractedFinding.objects.create(
        analysis_run=run,
        analysis_task_run=task,
        document_revision=revisions[1],
        source_candidate_key="project-set-ai",
        semantic_key="project-set-ai",
        category=ExtractedFinding.Category.PROJECT_FACT,
        subject="Grounded item",
        machine_value="Specified",
        normalized_machine_value="specified",
        machine_support=ExtractedFinding.Support.EXPLICIT,
        schema_version="v1",
    )
    page_task = AnalysisTaskRun.objects.create(
        analysis_run=run,
        document_page=page,
        task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
        input_mode=AnalysisTaskRun.InputMode.NATIVE_TEXT,
        status=AnalysisTaskRun.Status.SUCCEEDED,
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        input_metadata={"test": True},
    )
    FindingSource.objects.create(
        finding=ai,
        document_revision=revisions[1],
        document_page=page,
        analysis_task_run=page_task,
        source_key="project-set-ai-source",
        evidence_mode=FindingSource.EvidenceMode.NATIVE_TEXT,
        evidence_excerpt="Specified",
    )
    return run, (human, ai)


def test_dashboard_summary_matches_review_and_approval_state(organization, user, membership):
    project = create_project(organization, user)
    create_reviewed_document(project, user, "complete")
    create_reviewed_document(project, user, "attention", needs_attention=True)
    create_approval(project, user)
    create_approval(project, user, version=2)

    response = client_for(user).get(dashboard_url(organization))

    assert response.status_code == 200
    assert response.data["summary"] == {
        "active_projects": 1,
        "needs_attention": 1,
        "project_reviews_complete": 0,
        "approved_information": 2,
    }
    row = response.data["projects"][0]
    assert row["active_document_count"] == 2
    assert row["reviewed_document_count"] == 1
    assert row["review_mode"] == "document"
    assert row["project_review"] is None
    assert row["review"] == {
        "total": 2,
        "ai_handled": 0,
        "reviewed_by_user": 1,
        "needs_attention": 1,
        "conflicts": 0,
        "complete": False,
    }
    assert row["approved_snapshot"]["version"] == 2
    assert row["approved_snapshot_count"] == 2
    assert row["needs_attention"] is True
    assert "manifest" not in row["approved_snapshot"]
    assert "findings" not in row and "documents" not in row and "sources" not in row


def test_project_set_review_overrides_historical_document_runs(organization, user, membership):
    project = create_project(organization, user)
    first, _ = create_reviewed_document(project, user, "standalone-one")
    second, _ = create_reviewed_document(project, user, "standalone-two")
    extra, _ = create_reviewed_document(project, user, "outside-set")
    run, _ = create_project_set_review(project, user, [first, second])
    create_approval(project, user, version=4)

    response = client_for(user).get(dashboard_url(organization))

    assert response.status_code == 200
    assert response.data["summary"] == {
        "active_projects": 1,
        "needs_attention": 0,
        "project_reviews_complete": 1,
        "approved_information": 1,
    }
    row = response.data["projects"][0]
    assert row["active_document_count"] == 3
    assert row["reviewed_document_count"] == 0
    assert row["review_mode"] == "project_set"
    assert row["project_review"] == {
        "run_id": run.pk,
        "document_count": 2,
        "page_count": 12,
        "current": True,
    }
    assert row["review"] == {
        "total": 2,
        "ai_handled": 1,
        "reviewed_by_user": 1,
        "needs_attention": 0,
        "conflicts": 0,
        "complete": True,
    }
    assert row["approved_snapshot"]["version"] == 4
    assert extra.pk not in {first.pk, second.pk}


def test_project_set_conflict_and_changed_selection_require_attention(
    organization, user, membership
):
    project = create_project(organization, user)
    first, _ = create_reviewed_document(project, user, "first")
    second, _ = create_reviewed_document(project, user, "second")
    run, findings = create_project_set_review(project, user, [first, second])
    conflict = IntelligenceConflict.objects.create(
        project=project,
        analysis_run=run,
        semantic_key="project-set-conflict",
        participant_key="project-set-conflict",
        explanation="Test conflict",
    )
    conflict.findings.set(findings)

    response = client_for(user).get(dashboard_url(organization))
    row = response.data["projects"][0]
    assert row["review"]["conflicts"] == 1
    assert row["review"]["complete"] is False
    assert row["needs_attention"] is True

    IntelligenceConflict.objects.filter(pk=conflict.pk).update(
        status=IntelligenceConflict.Status.DISMISSED
    )
    ProjectDocumentSelection.objects.filter(document=second).update(is_included=False)
    response = client_for(user).get(dashboard_url(organization))
    row = response.data["projects"][0]
    assert row["project_review"]["current"] is False
    assert row["review"]["complete"] is False
    assert row["needs_attention"] is True


def test_project_set_unresolved_finding_requires_attention(organization, user, membership):
    project = create_project(organization, user)
    first, _ = create_reviewed_document(project, user, "first")
    second, _ = create_reviewed_document(project, user, "second")
    _, findings = create_project_set_review(project, user, [first, second])
    FindingReview.objects.create(
        finding=findings[1],
        reviewer=user,
        decision=FindingReview.Decision.NEEDS_CLARIFICATION,
    )

    response = client_for(user).get(dashboard_url(organization))

    assert response.status_code == 200
    row = response.data["projects"][0]
    assert row["review"]["needs_attention"] == 1
    assert row["review"]["complete"] is False
    assert row["needs_attention"] is True


def test_dashboard_is_organization_scoped_and_viewer_readable(organization, user, membership):
    visible = create_project(organization, user)
    create_reviewed_document(visible, user, "visible")
    other = Organization.objects.create(name="Other", slug="other")
    hidden = create_project(other, user, "BB-HIDDEN")
    create_reviewed_document(hidden, user, "hidden")
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))

    response = client_for(user).get(dashboard_url(organization))
    assert response.status_code == 200
    assert [row["project"]["id"] for row in response.data["projects"]] == [visible.pk]

    membership.is_active = False
    membership.save(update_fields=("is_active",))
    assert client_for(user).get(dashboard_url(organization)).status_code == 403


def test_dashboard_counts_conflict_groups_not_participants(organization, user, membership):
    project = create_project(organization, user)
    _, run = create_reviewed_document(project, user, "conflicted")
    first = ExtractedFinding.objects.get(analysis_run=run)
    second = ExtractedFinding.objects.create(
        analysis_run=run,
        analysis_task_run=first.analysis_task_run,
        document_revision=first.document_revision,
        source_candidate_key="second-conflicted",
        semantic_key="second-conflicted",
        category=ExtractedFinding.Category.PROJECT_FACT,
        subject="conflicted",
        machine_value="Other value",
        normalized_machine_value="other value",
        machine_support=ExtractedFinding.Support.EXPLICIT,
        schema_version="v1",
    )
    conflict = IntelligenceConflict.objects.create(
        project=project,
        analysis_run=run,
        semantic_key="conflicted",
        participant_key="conflicted",
        explanation="Test conflict group",
    )
    conflict.findings.set([first, second])

    response = client_for(user).get(dashboard_url(organization))

    assert response.status_code == 200
    assert response.data["projects"][0]["review"]["conflicts"] == 1


def test_dashboard_excludes_archived_projects_and_bounds_queries(organization, user, membership):
    for index in range(3):
        project = create_project(organization, user, f"BB-DASH-{index}")
        for document_index in range(3):
            create_reviewed_document(project, user, f"doc-{index}-{document_index}")
    create_project(organization, user, "BB-ARCHIVED", active=False)

    with CaptureQueriesContext(connection) as queries:
        response = client_for(user).get(dashboard_url(organization))

    assert response.status_code == 200
    assert len(response.data["projects"]) == 3
    assert len(queries) <= 9


def test_dashboard_activity_is_bounded_and_excludes_raw_metadata(organization, user, membership):
    project = create_project(organization, user)
    for index in range(12):
        AuditEvent.objects.create(
            organization=organization,
            project=project,
            actor=user,
            action_code=f"project.event_{index}",
            target_type="project",
            target_id=str(project.pk),
            metadata={"private": "not exposed"},
        )

    response = client_for(user).get(activity_url(organization))

    assert response.status_code == 200
    assert len(response.data["results"]) == 8
    assert all("metadata" not in event for event in response.data["results"])
