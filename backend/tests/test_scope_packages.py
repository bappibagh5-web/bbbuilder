import hashlib
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.analysis.models import (
    AnalysisRun,
    AnalysisTaskRun,
    ExtractedFinding,
    ProjectIntelligenceApproval,
    ProjectIntelligenceSnapshot,
    ProjectIntelligenceSnapshotEntry,
    ProjectIntelligenceSnapshotSource,
)
from apps.documents.models import Document, DocumentPage, DocumentRevision, FileAsset, ProjectFile
from apps.organizations.models import Membership, Organization
from apps.projects.models import AuditEvent, Project
from apps.scope_packages.models import ScopePackage, ScopePackageSource, ScopePackageVersion
from apps.scope_packages.services import generate_scope_packages, revise_scope_package
from apps.scope_packages.taxonomy import (
    FIRE_PROTECTION,
    GENERAL,
    HVAC,
    PLUMBING,
    trades_for_entry,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-SCOPE-001",
        name="Scope Test",
        project_timezone="America/Vancouver",
        status=Project.Status.HUMAN_SCOPE_REVIEW,
    )


@pytest.fixture
def approved_snapshot(project, user):
    content = b"scope source"
    asset = FileAsset.objects.create(
        organization=project.organization,
        bucket="test",
        storage_key="scope/source.pdf",
        original_filename="source.pdf",
        declared_mime_type="application/pdf",
        detected_mime_type="application/pdf",
        byte_size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        created_by=user,
    )
    project_file = ProjectFile.objects.create(project=project, file_asset=asset, created_by=user)
    document = Document.objects.create(
        project=project, title="Mechanical Drawings", category="drawings", created_by=user
    )
    revision = DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        revision_label="R1",
        source_filename="source.pdf",
        created_by=user,
    )
    page = DocumentPage.objects.create(
        document_revision=revision,
        page_number=1,
        page_label="M01",
        width_points=612,
        height_points=792,
        native_text="Provide mechanical ductwork.",
        native_text_char_count=28,
        has_native_text=True,
        parser_name="PyMuPDF",
        parser_version="1.28.2",
    )
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
    )
    task = AnalysisTaskRun.objects.create(
        analysis_run=run,
        document_page=page,
        task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
        input_mode=AnalysisTaskRun.InputMode.NATIVE_TEXT,
        status=AnalysisTaskRun.Status.SUCCEEDED,
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        input_metadata={"page_number": 1},
    )
    finding = ExtractedFinding.objects.create(
        analysis_run=run,
        analysis_task_run=task,
        document_revision=revision,
        source_candidate_key="a" * 64,
        semantic_key="mechanical-ductwork",
        category=ExtractedFinding.Category.SCOPE_TRADE,
        subject="Mechanical",
        machine_value="Provide mechanical ductwork.",
        normalized_machine_value="provide mechanical ductwork.",
        machine_support=ExtractedFinding.Support.EXPLICIT,
        schema_version="v1",
    )
    snapshot = ProjectIntelligenceSnapshot.objects.create(
        project=project,
        version=1,
        fingerprint="b" * 64,
        manifest={"sources": [run.pk]},
        summary_counts={"included": 1},
        created_by=user,
    )
    source = ProjectIntelligenceSnapshotSource.objects.create(
        snapshot=snapshot, analysis_run=run, document_revision=revision
    )
    ProjectIntelligenceSnapshotEntry.objects.create(
        snapshot=snapshot,
        snapshot_source=source,
        finding=finding,
        decision=ProjectIntelligenceSnapshotEntry.Decision.MACHINE_HANDLED,
        effective_value=finding.machine_value,
        semantic_key=finding.semantic_key,
        category=finding.category,
        included_in_intelligence=True,
    )
    ProjectIntelligenceApproval.objects.create(
        project=project, snapshot=snapshot, approver=user, readiness_result={"eligible": True}
    )
    return snapshot


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_generation_requires_approved_project_information(project, user, approved_snapshot):
    unapproved = ProjectIntelligenceSnapshot.objects.create(
        project=project,
        version=2,
        fingerprint="c" * 64,
        manifest={"test": "unapproved"},
        summary_counts={"included": 0},
        created_by=user,
    )
    with pytest.raises(ValidationError, match="approved project information"):
        generate_scope_packages(project=project, snapshot=unapproved, actor=user)
    assert ScopePackage.objects.count() == 0


def test_approved_snapshot_generation_is_idempotent_and_traceable(project, user, approved_snapshot):
    created, existing = generate_scope_packages(
        project=project, snapshot=approved_snapshot, actor=user
    )
    repeated_created, repeated_existing = generate_scope_packages(
        project=project, snapshot=approved_snapshot, actor=user
    )
    package = created[0]
    assert len(created) == 1 and existing == []
    assert repeated_created == [] and repeated_existing == [package]
    assert package.current_version.version == 1
    assert package.current_version.status == ScopePackageVersion.Status.DRAFT
    assert package.trade_key == "hvac-mechanical"
    assert package.trade_category == "HVAC / Mechanical"
    assert package.current_version.inclusions == ["Mechanical: Provide mechanical ductwork."]
    assert package.current_version.sources.count() == 1
    assert package.source_snapshot_id == approved_snapshot.pk


@pytest.mark.parametrize(
    ("subject", "value", "expected"),
    [
        ("Ventilation scope", "Provide ductwork and diffusers", (HVAC,)),
        ("Plumbing scope", "Provide water heater and hub drain", (PLUMBING,)),
        ("Sprinkler scope", "Install sprinkler piping to NFPA 13", (FIRE_PROTECTION,)),
        ("Drawing issue date", "10 April 2026", (GENERAL,)),
        (
            "Field verification",
            "Verify ductwork and plumbing locations before work",
            (PLUMBING, HVAC),
        ),
    ],
)
def test_controlled_taxonomy_groups_findings_by_trade(subject, value, expected):
    entry = SimpleNamespace(finding=SimpleNamespace(subject=subject), effective_value=value)
    assert trades_for_entry(entry) == expected


def test_regeneration_supersedes_untouched_legacy_draft_but_preserves_human_edit(
    project, user, approved_snapshot
):
    untouched = ScopePackage.objects.create(
        organization=project.organization,
        project=project,
        source_snapshot=approved_snapshot,
        trade_key="category-project-fact",
        trade_category="Project fact",
        created_by=user,
        updated_by=user,
    )
    untouched.current_version = ScopePackageVersion.objects.create(
        package=untouched,
        version=1,
        title="Project fact Scope",
        inclusions=["Legacy"],
        created_by=user,
    )
    untouched.save(update_fields=("current_version", "updated_at"))
    edited = ScopePackage.objects.create(
        organization=project.organization,
        project=project,
        source_snapshot=approved_snapshot,
        trade_key="category-responsibility",
        trade_category="Responsibility",
        created_by=user,
        updated_by=user,
    )
    edited.current_version = ScopePackageVersion.objects.create(
        package=edited,
        version=1,
        title="Responsibility Scope",
        inclusions=["Legacy"],
        created_by=user,
    )
    edited.save(update_fields=("current_version", "updated_at"))
    revise_scope_package(package=edited, actor=user, values={"description": "Human-reviewed scope"})

    created, _ = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)
    untouched.refresh_from_db()
    edited.refresh_from_db()
    assert len(created) == 1
    assert untouched.lifecycle == ScopePackage.Lifecycle.SUPERSEDED
    assert edited.lifecycle == ScopePackage.Lifecycle.ACTIVE
    assert edited.current_version.description == "Human-reviewed scope"
    assert AuditEvent.objects.filter(action_code="scope_package.generated").count() == 1


def test_edits_and_ready_actions_append_versions_without_rebinding_snapshot(
    project, user, approved_snapshot
):
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    original = package.current_version
    edited, created = revise_scope_package(
        package=package,
        actor=user,
        values={"title": "Reviewed Mechanical Scope", "exclusions": ["Controls by others"]},
    )
    assert created and edited.version == 2 and edited.status == "draft"
    ready, ready_created = revise_scope_package(
        package=package, actor=user, values={}, mark_ready=True
    )
    assert ready_created and ready.version == 3 and ready.status == "ready"
    original.refresh_from_db()
    assert original.title == "HVAC / Mechanical Scope" and original.status == "draft"
    assert ScopePackageVersion.objects.filter(package=package).count() == 3
    assert ScopePackageSource.objects.filter(package_version__package=package).count() == 3
    assert package.source_snapshot_id == approved_snapshot.pk


@pytest.mark.parametrize("role", [Membership.Role.ADMIN, Membership.Role.ESTIMATOR_OPERATOR])
def test_admin_and_estimator_can_generate_edit_and_mark_ready(
    project, user, membership, approved_snapshot, role
):
    membership.role = role
    membership.save(update_fields=("role",))
    base = {"organization_slug": project.organization.slug, "project_pk": project.pk}
    response = client_for(user).post(
        reverse("scope-package-generate", kwargs=base),
        {"snapshot_id": approved_snapshot.pk},
        format="json",
    )
    assert response.status_code == 201
    package_id = response.data["packages"][0]["id"]
    detail = reverse("scope-package-detail", kwargs={**base, "package_pk": package_id})
    assert client_for(user).patch(detail, {"title": "Edited"}, format="json").status_code == 200
    ready = reverse("scope-package-ready", kwargs={**base, "package_pk": package_id})
    first = client_for(user).post(ready, {}, format="json")
    assert first.status_code == 201
    assert first.data["current_version"]["status"] == "ready"
    assert first.data["current_version"]["version"] == 3
    assert client_for(user).post(ready, {}, format="json").status_code == 200
    assert ScopePackageVersion.objects.filter(package_id=package_id).count() == 3


def test_viewer_is_read_only(project, user, membership, approved_snapshot):
    generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    base = {"organization_slug": project.organization.slug, "project_pk": project.pk}
    listing = reverse("scope-package-list", kwargs=base)
    generate = reverse("scope-package-generate", kwargs=base)
    package = ScopePackage.objects.get()
    detail = reverse("scope-package-detail", kwargs={**base, "package_pk": package.pk})
    assert client_for(user).get(listing).status_code == 200
    assert client_for(user).post(generate, {"snapshot_id": approved_snapshot.pk}).status_code == 403
    assert client_for(user).patch(detail, {"title": "No"}, format="json").status_code == 403
    assert client_for(user).delete(detail).status_code == 405


def test_cross_organization_scope_isolation(project, user, membership, approved_snapshot):
    generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)
    other_org = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(user=user, organization=other_org, role=Membership.Role.ADMIN)
    other_project = Project.objects.create(
        organization=other_org,
        created_by=user,
        project_number="OTHER-1",
        name="Other",
        project_timezone="UTC",
    )
    url = reverse(
        "scope-package-detail",
        kwargs={
            "organization_slug": other_org.slug,
            "project_pk": other_project.pk,
            "package_pk": ScopePackage.objects.get().pk,
        },
    )
    assert client_for(user).get(url).status_code == 404


def test_historical_approved_snapshot_binding_is_preserved(project, user, approved_snapshot):
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    newer = ProjectIntelligenceSnapshot.objects.create(
        project=project,
        version=2,
        fingerprint="d" * 64,
        manifest={"test": "newer-approved"},
        summary_counts={"included": 0},
        created_by=user,
    )
    ProjectIntelligenceApproval.objects.create(
        project=project, snapshot=newer, approver=user, readiness_result={"eligible": True}
    )
    revise_scope_package(package=package, actor=user, values={"description": "Human edit"})
    package.refresh_from_db()
    assert package.source_snapshot_id == approved_snapshot.pk
