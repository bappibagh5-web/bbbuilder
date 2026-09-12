import hashlib
import json
import urllib.error
from collections import Counter
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.analysis.models import (
    AnalysisRun,
    AnalysisTaskRun,
    ExtractedFinding,
    FindingSource,
    ProjectIntelligenceApproval,
    ProjectIntelligenceSnapshot,
    ProjectIntelligenceSnapshotEntry,
    ProjectIntelligenceSnapshotProvenance,
    ProjectIntelligenceSnapshotSource,
)
from apps.contractors.enrichment import enrich_company_contacts
from apps.contractors.models import (
    Company,
    Contact,
    DiscoveryRequest,
    ScopeContractorCandidate,
    TradeCapability,
)
from apps.contractors.providers import (
    BUSINESS_RADIUS_MILES,
    GOOGLE_MAX_PAGES_PER_QUERY,
    GOOGLE_MAX_REQUESTS,
    ContractorProviderError,
    ContractorResult,
    ContractorSearchOutcome,
    FakeContractorDiscoveryProvider,
    GooglePlacesContractorDiscoveryProvider,
    SearchCenter,
    bounding_rectangle,
    build_search_queries,
    great_circle_miles,
    map_google_place,
)
from apps.contractors.ranking import rank_candidate
from apps.contractors.services import (
    create_contact,
    dedupe_company,
    discover_contractors,
    internal_companies,
    project_location_query,
)
from apps.documents.models import Document, DocumentPage, DocumentRevision, FileAsset, ProjectFile
from apps.organizations.models import Membership, Organization
from apps.projects.models import AuditEvent, Project
from apps.scope_packages.coverage_preview import (
    PREVIEW_RULE_VERSION,
    _atomic_values,
    _classify,
    _client_title,
    _responsibility,
    build_scope_coverage_preview,
)
from apps.scope_packages.models import (
    ScopeItem,
    ScopeItemSource,
    ScopePackage,
    ScopePackageSource,
    ScopePackageVersion,
)
from apps.scope_packages.services import (
    SCOPE_PLAN_CHANGED_MESSAGE,
    generate_scope_packages,
    generate_scope_plan_packages,
    revise_scope_package,
)
from apps.scope_packages.taxonomy import (
    FIRE_PROTECTION,
    GENERAL,
    HVAC,
    PLUMBING,
    SPECIALTY_EQUIPMENT,
    scope_items_for_entry,
    trades_for_entry,
)
from apps.scope_packages.trades import (
    CONTRACTOR_ELIGIBLE_TRADE_KEYS,
    TRADE_CHOICES,
    TRADE_QUERY_TERMS,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-SCOPE-001",
        name="Scope Test",
        city="Thunder Bay",
        province_state="Ontario",
        country="CA",
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
    finding_source = FindingSource.objects.create(
        finding=finding,
        document_revision=revision,
        document_page=page,
        analysis_task_run=task,
        source_key="c" * 64,
        evidence_mode=FindingSource.EvidenceMode.NATIVE_TEXT,
        evidence_excerpt="Provide mechanical ductwork.",
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
    entry = ProjectIntelligenceSnapshotEntry.objects.create(
        snapshot=snapshot,
        snapshot_source=source,
        finding=finding,
        decision=ProjectIntelligenceSnapshotEntry.Decision.MACHINE_HANDLED,
        effective_value=finding.machine_value,
        semantic_key=finding.semantic_key,
        category=finding.category,
        included_in_intelligence=True,
    )
    ProjectIntelligenceSnapshotProvenance.objects.create(
        snapshot_entry=entry,
        finding_source=finding_source,
        document_revision=revision,
        document_page=page,
        analysis_task_run=task,
    )
    ProjectIntelligenceApproval.objects.create(
        project=project, snapshot=snapshot, approver=user, readiness_result={"eligible": True}
    )
    return snapshot


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def preview_entry(subject, value, *, category="scope_trade", discipline="general"):
    entry = SimpleNamespace(
        category=category,
        effective_value=value,
        finding=SimpleNamespace(subject=subject),
    )
    provenance = [
        SimpleNamespace(
            document_revision=SimpleNamespace(
                document=SimpleNamespace(title="Project source", discipline=discipline)
            ),
            finding_source=SimpleNamespace(evidence_excerpt=value, visual_evidence_description=""),
        )
    ]
    return entry, provenance


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("Provide miscellaneous metal steel angles.", "Miscellaneous Metals"),
        ("Supply steel stud partition framing.", "Steel Stud Framing"),
        ("Provide plywood backing and blocking.", "Backing / Blocking"),
        ("Install gypsum board drywall.", "Drywall"),
        ("Tape joints with joint compound.", "Mudding & Taping"),
        ("Install suspended acoustic ceiling tile.", "T-Bar / ACT Ceilings"),
        ("Provide door frames and door hardware.", "Doors / Frames / Hardware"),
        ("Install glazing at the storefront.", "Glazing / Storefront"),
        ("Provide millwork and casework.", "Millwork"),
        ("Install floor tile and carpet flooring.", "Flooring"),
        ("Apply painting and wall finish.", "Painting / Finishes"),
        ("Install washroom accessory specialties.", "Specialties"),
        ("Connect domestic water plumbing.", "Plumbing"),
        ("Install HVAC duct and diffuser.", "HVAC / Mechanical"),
        ("Relocate fire protection sprinklers.", "Fire Protection / Sprinklers"),
        ("Install lighting luminaires.", "Lighting"),
        ("Connect the fire alarm shutdown interface.", "Fire Alarm"),
        ("Provide low voltage data cabling.", "Low Voltage / Data"),
        ("Install CCTV security cameras.", "Security"),
        ("Provide audio visual speakers.", "AV"),
        ("Connect illuminated signage.", "Signage"),
        ("Patch roof membrane around roof curb.", "Roofing"),
        ("Firestop the rated penetration.", "Firestopping"),
        ("Complete civil site trenching.", "Civil / Site Work"),
        ("Provide structural equipment supports.", "Structural"),
        ("Demolish and remove existing partition.", "Demolition"),
        ("Submit closeout warranty and as-built records.", "Closeout"),
        ("Provide electrical feeder and disconnect.", "Electrical Power"),
    ),
)
def test_scope_coverage_preview_taxonomy(text, expected):
    entry, provenance = preview_entry(expected, text)
    destinations, _ = _classify(entry, provenance)
    assert expected in {label for _, label in destinations}


def test_scope_coverage_preview_avoids_substring_false_matches():
    entry, provenance = preview_entry("Controls", "Provide controlled access sequence.")
    destinations, _ = _classify(entry, provenance)
    assert "Lighting" not in {label for _, label in destinations}


def test_scope_coverage_preview_splits_only_explicit_bulleted_obligations():
    value = "Paint existing ducts to match ceiling\n- Provide copper branch conductors"
    assert _atomic_values(value) == [
        "Paint existing ducts to match ceiling",
        "Provide copper branch conductors",
    ]


def test_scope_coverage_preview_replaces_internal_subject_with_obligation_title():
    entry, _ = preview_entry(
        "Electrical: bid_condition",
        "Provide 24-hour power and data connection for screens",
        category="bid_condition",
    )
    assert _client_title(entry, entry.effective_value) == entry.effective_value


def test_scope_coverage_preview_keeps_passive_fire_rating_work_out_of_sprinklers():
    entry, provenance = preview_entry(
        "Fire protection and refurbishment",
        "Restore beam fire protection after stud installation",
        category="scope_trade",
    )
    destinations, _ = _classify(entry, provenance)
    labels = {label for _, label in destinations}
    assert "Fire Protection / Sprinklers" not in labels
    assert "General Requirements" in labels


@pytest.mark.parametrize(
    ("subject", "value"),
    (
        ("Electrical: project_fact", "Do not scale drawing."),
        ("Drawing issue - For Construction", "For Construction"),
        ("Electrical: project_fact", "The GC shall verify dimensions on site."),
    ),
)
def test_scope_coverage_preview_does_not_infer_electrical_from_source_discipline(subject, value):
    entry, provenance = preview_entry(
        subject, value, category="project_fact", discipline="electrical"
    )
    destinations, _ = _classify(entry, provenance)
    assert "Electrical Power" not in {label for _, label in destinations}


@pytest.mark.parametrize(
    ("subject", "value", "expected"),
    (
        ("Directional security cameras", "Owner supplied cameras installed by Nutech", "Security"),
        (
            "Door cylinders",
            "Cylinders supplied and installed by locksmith",
            "Doors / Frames / Hardware",
        ),
        ("55-inch Digital screens", "Digital screens provided by JD", "AV"),
        ("Wall-mounted lightbox", "Lightbox LB1 provided by Property", "Signage"),
        ("Security sensors", "Owner supplied security sensors", "Security"),
        ("Sliding shutter", "Supply and install new Aeroflex sliding shutter", "Specialties"),
        ("Architectural / Interiors: project_fact", "Install gypsum board drywall", "Drywall"),
    ),
)
def test_scope_coverage_preview_classifies_by_effective_scope(subject, value, expected):
    entry, provenance = preview_entry(subject, value, category="project_fact")
    destinations, _ = _classify(entry, provenance)
    assert expected in {label for _, label in destinations}


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("G.C. to provide all wood blocking and plywood", "supply_install"),
        ("G.C. is responsible for installation of backing", "supply_install"),
        ("By landlord", "landlord_supplied"),
        ("Owner supplied", "owner_supplied"),
        ("This contractor shall provide the equipment", "supply_install"),
        ("Structural engineer to confirm support height", "by_others"),
    ),
)
def test_scope_coverage_preview_extracts_explicit_responsibility(text, expected):
    assert _responsibility(_normalized_for_test(text)) == expected


def test_scope_coverage_preview_recognizes_electrical_contractor_cost_responsibility():
    assert _responsibility("costs charged to the electrical contractor.") == "supply_install"


def test_scope_coverage_preview_keeps_structural_field_review_out_of_hvac():
    entry, provenance = preview_entry(
        "HVAC / Mechanical: project_fact",
        "Do not cover framing with finishes until RJC field review is complete. "
        "Contractor shall notify RJC for field review.",
        category="project_fact",
        discipline="mechanical",
    )
    destinations, _ = _classify(entry, provenance)
    labels = {label for _, label in destinations}
    assert "Structural" in labels
    assert "HVAC / Mechanical" not in labels


def _normalized_for_test(value):
    return " ".join(value.casefold().split())


def test_scope_coverage_preview_preserves_uncertainty_and_multitrade_coordination():
    entry, provenance = preview_entry(
        "RTU coordination",
        "Coordinate RTU ductwork, electrical feeder, structural roof opening, "
        "fire alarm shutdown interface, and roof membrane flashing; responsibility TBC.",
        category="open_question",
    )
    destinations, text = _classify(entry, provenance)
    labels = {label for _, label in destinations}
    assert {
        "HVAC / Mechanical",
        "Electrical Power",
        "Structural",
        "Fire Alarm",
        "Roofing",
    } <= labels
    assert _responsibility(text) == "unclear"


def test_scope_coverage_preview_reports_unmapped_instead_of_manufacturing_scope():
    entry, provenance = preview_entry(
        "Unclassified requirement", "Confirm unusual project condition.", category="project_fact"
    )
    destinations, _ = _classify(entry, provenance)
    assert destinations == ()


def test_scope_coverage_preview_is_read_only_and_repeatable(
    project, user, membership, approved_snapshot
):
    url = reverse(
        "scope-coverage-preview",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    before = (
        ScopePackage.objects.count(),
        ScopePackageVersion.objects.count(),
        ScopeItem.objects.count(),
    )
    first = client_for(user).get(url)
    second = client_for(user).get(url)
    assert first.status_code == second.status_code == 200
    assert first.data == second.data
    assert first.data["source_snapshot_id"] == approved_snapshot.pk
    assert first.data["taxonomy_version"] == PREVIEW_RULE_VERSION
    assert first.data["proposed_package_count"] == 1
    assert first.data["packages"][0]["name"] == "HVAC / Mechanical"
    provenance = first.data["packages"][0]["items"][0]["provenance"][0]
    assert provenance["page_number"] == 1
    assert provenance["evidence_excerpt"] == "Provide mechanical ductwork."
    assert before == (
        ScopePackage.objects.count(),
        ScopePackageVersion.objects.count(),
        ScopeItem.objects.count(),
    )
    assert client_for(user).post(url, {}).status_code == 405


def test_scope_coverage_preview_selects_latest_approved_not_newer_unapproved(
    project, user, approved_snapshot
):
    ProjectIntelligenceSnapshot.objects.create(
        project=project,
        version=2,
        fingerprint="d" * 64,
        manifest={"test": "must not be consumed"},
        summary_counts={"included": 0},
        created_by=user,
    )
    preview = build_scope_coverage_preview(project)
    assert preview["source_snapshot_id"] == approved_snapshot.pk
    assert preview["source_snapshot_version"] == 1


def test_scope_coverage_preview_consolidates_equivalent_permit_obligations_with_all_sources(
    project, user, approved_snapshot
):
    snapshot_source = approved_snapshot.sources.get()
    revision = snapshot_source.document_revision
    page = revision.pages.get(page_number=1)
    task = AnalysisTaskRun.objects.get(analysis_run=snapshot_source.analysis_run)
    for index, wording in enumerate(
        (
            "Obtain landlord review and permit approval.",
            "Coordinate required landlord permit review and approval.",
        ),
        start=1,
    ):
        finding = ExtractedFinding.objects.create(
            analysis_run=snapshot_source.analysis_run,
            analysis_task_run=task,
            document_revision=revision,
            source_candidate_key=str(index) * 64,
            semantic_key=f"landlord-permit-{index}",
            category=ExtractedFinding.Category.PERMIT_INSPECTION,
            subject="Landlord permit approval",
            machine_value=wording,
            normalized_machine_value=wording.casefold(),
            machine_support=ExtractedFinding.Support.EXPLICIT,
            schema_version="v1",
        )
        finding_source = FindingSource.objects.create(
            finding=finding,
            document_revision=revision,
            document_page=page,
            analysis_task_run=task,
            source_key=str(index + 2) * 64,
            evidence_mode=FindingSource.EvidenceMode.NATIVE_TEXT,
            evidence_excerpt="Provide mechanical ductwork.",
        )
        entry = ProjectIntelligenceSnapshotEntry.objects.create(
            snapshot=approved_snapshot,
            snapshot_source=snapshot_source,
            finding=finding,
            decision=ProjectIntelligenceSnapshotEntry.Decision.MACHINE_HANDLED,
            effective_value=wording,
            semantic_key=finding.semantic_key,
            category=finding.category,
            included_in_intelligence=True,
        )
        ProjectIntelligenceSnapshotProvenance.objects.create(
            snapshot_entry=entry,
            finding_source=finding_source,
            document_revision=revision,
            document_page=page,
            analysis_task_run=task,
        )

    preview = build_scope_coverage_preview(project)
    general = preview["project_wide_requirements"]
    permit = next(
        item
        for item in general["items"]
        if item["item_key"] == "coordinate-landlord-review-and-permit-approval"
    )
    assert len(permit["approved_entry_ids"]) == 2
    assert len(permit["provenance"]) == 2
    assert preview["duplicate_obligations_consolidated"] == 1
    assert preview["project_wide_requirement_count"] == general["scope_item_count"]
    assert all(item["trade_key"] != "general-requirements" for item in preview["packages"])
    assert preview["proposed_package_count"] == len(preview["packages"])


def test_scope_coverage_preview_selects_newest_approved_version(project, user, approved_snapshot):
    newest = ProjectIntelligenceSnapshot.objects.create(
        project=project,
        version=2,
        fingerprint="e" * 64,
        manifest={"test": "newest approved"},
        summary_counts={"included": 0},
        created_by=user,
    )
    ProjectIntelligenceApproval.objects.create(
        project=project,
        snapshot=newest,
        approver=user,
        readiness_result={"eligible": True},
    )
    preview = build_scope_coverage_preview(project)
    assert preview["source_snapshot_id"] == newest.pk
    assert preview["source_snapshot_version"] == 2


def test_scope_plan_fingerprint_is_deterministic(project, approved_snapshot):
    first = build_scope_coverage_preview(project)
    second = build_scope_coverage_preview(project)
    assert first["plan_fingerprint"] == second["plan_fingerprint"]
    assert len(first["plan_fingerprint"]) == 64


def test_canonical_generation_persists_preview_plan_and_is_idempotent(
    project, user, approved_snapshot
):
    preview = build_scope_coverage_preview(project)
    created, existing, persisted_plan = generate_scope_plan_packages(
        project=project,
        actor=user,
        expected_plan_fingerprint=preview["plan_fingerprint"],
        expected_project_information_version=preview["source_snapshot_version"],
    )
    repeated_created, repeated_existing, repeated_plan = generate_scope_plan_packages(
        project=project,
        actor=user,
        expected_plan_fingerprint=preview["plan_fingerprint"],
        expected_project_information_version=preview["source_snapshot_version"],
    )
    assert len(created) == preview["proposed_package_count"]
    assert existing == []
    assert repeated_created == []
    assert {package.pk for package in repeated_existing} == {package.pk for package in created}
    assert (
        persisted_plan["plan_fingerprint"]
        == repeated_plan["plan_fingerprint"]
        == preview["plan_fingerprint"]
    )
    assert (
        ScopeItem.objects.filter(package_version__package__in=created).count()
        == preview["proposed_scope_item_count"]
    )
    assert all(package.current_version.status == "draft" for package in created)
    assert all(package.plan_fingerprint == preview["plan_fingerprint"] for package in created)
    item = ScopeItem.objects.get(package_version__package__in=created)
    preview_item = preview["packages"][0]["items"][0]
    assert item.description == preview_item["description"]
    assert item.responsibility == preview_item["responsibility"]
    assert item.coordination_required == preview_item["coordination_required"]
    assert set(item.sources.values_list("snapshot_provenance_id", flat=True)) == {
        source["snapshot_provenance_id"] for source in preview_item["provenance"]
    }


def test_canonical_generation_rejects_stale_preview(project, user, approved_snapshot):
    preview = build_scope_coverage_preview(project)
    with pytest.raises(ValidationError, match="Project information or proposed scope"):
        generate_scope_plan_packages(
            project=project,
            actor=user,
            expected_plan_fingerprint="0" * 64,
            expected_project_information_version=preview["source_snapshot_version"],
        )
    assert SCOPE_PLAN_CHANGED_MESSAGE.startswith("Project information")
    assert ScopePackage.objects.count() == 0


def test_scope_coverage_preview_requires_approved_information(project, user, membership):
    url = reverse(
        "scope-coverage-preview",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    response = client_for(user).get(url)
    assert response.status_code == 409
    assert "Approved project information" in response.data["detail"]


def test_scope_coverage_preview_is_viewer_readable_and_organization_scoped(
    project, approved_snapshot, django_user_model
):
    viewer = django_user_model.objects.create_user(
        email="scope-preview-viewer@example.com", password="not-a-secret"
    )
    Membership.objects.create(
        user=viewer, organization=project.organization, role=Membership.Role.VIEWER
    )
    url = reverse(
        "scope-coverage-preview",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    assert client_for(viewer).get(url).status_code == 200
    assert client_for(viewer).post(url, {}).status_code == 405

    other = Organization.objects.create(name="Other Scope Org", slug="other-scope-org")
    Membership.objects.create(user=viewer, organization=other, role=Membership.Role.VIEWER)
    wrong_org_url = reverse(
        "scope-coverage-preview",
        kwargs={"organization_slug": other.slug, "project_pk": project.pk},
    )
    assert client_for(viewer).get(wrong_org_url).status_code == 404


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
    assert package.current_version.scope_items.count() == 1
    assert package.current_version.scope_items.get().sources.count() == 1
    assert package.source_snapshot_id == approved_snapshot.pk


def test_generation_requires_frozen_snapshot_provenance(project, user, approved_snapshot):
    ProjectIntelligenceSnapshotProvenance.objects.filter(
        snapshot_entry__snapshot=approved_snapshot
    ).delete()
    with pytest.raises(ValidationError, match="has no frozen provenance"):
        generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)
    assert ScopePackage.objects.count() == 0


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


def test_regeneration_supersedes_legacy_generation_but_preserves_human_edit_history(
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
    assert edited.lifecycle == ScopePackage.Lifecycle.SUPERSEDED
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
    assert ScopeItem.objects.filter(package_version__package=package).count() == 3
    assert ScopeItemSource.objects.filter(scope_item__package_version__package=package).count() == 3
    assert package.source_snapshot_id == approved_snapshot.pk


def test_security_grilles_are_not_misclassified_as_hvac():
    entry = SimpleNamespace(
        pk=1,
        finding=SimpleNamespace(subject="Responsibility Schedule - Mobilflex"),
        effective_value="MOBILFLEX to install security grilles (JD supply)",
    )
    definitions = scope_items_for_entry(entry)
    assert len(definitions) == 1
    assert definitions[0].trade == SPECIALTY_EQUIPMENT
    assert definitions[0].title == "Install owner-supplied security grilles"
    assert definitions[0].responsibility == "owner_supplied"


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("Supply and install the new unit.", "supply_install"),
        ("Install owner-supplied equipment.", "owner_supplied"),
        ("Installation only; equipment furnished separately.", "install_only"),
        ("Landlord-supplied controls package.", "landlord_supplied"),
        ("Existing diffusers to remain.", "existing_to_remain"),
        ("Relocate and reuse the existing device.", "relocate_reuse"),
        ("Final connection by others.", "by_others"),
        ("Coordinate permit requirements.", "unclear"),
    ),
)
def test_scope_item_responsibility_is_deterministic(value, expected):
    entry = SimpleNamespace(
        pk=1,
        finding=SimpleNamespace(subject="General Contractor - verify dimensions and levels"),
        effective_value=value,
    )
    definitions = scope_items_for_entry(entry)
    assert definitions
    assert {definition.responsibility for definition in definitions} == {expected}


def test_scope_item_decomposition_creates_multiple_grounded_items():
    entry = SimpleNamespace(
        pk=1,
        finding=SimpleNamespace(subject="Demolition responsibilities"),
        effective_value="Demolish, dispose and coordinate MEP demolition.",
    )
    definitions = scope_items_for_entry(entry)
    assert len(definitions) == 5
    assert {item.item_type for item in definitions} == {"demolition", "coordination"}


def test_jd_intercity_v2_rules_predict_ten_trades_and_thirty_six_items():
    subjects = (
        "Drawing issuance / purpose and dates",
        "Permit responsibility / scope",
        "Owner-supplied materials (OSM) handling",
        "General Contractor - verify dimensions and levels",
        "Demolition responsibilities",
        "Controlled substance removal",
        "Landlord deliverable - vanilla shell",
        "Survey after demolition timing",
        "Plumbing fixtures provided",
        "Shopfront fascia and finishes",
        "Concealed blocking & bracing",
        "Footwear ordering screens (owner-supplied)",
        "Owner-supplied security/AV installers and contacts",
        "Responsibility Schedule - Citiloc re-keying",
        "Responsibility Schedule - Mobilflex",
        "Unistrut and threaded rod for suspended items",
        "Track lighting mounting",
    )
    counts = Counter()
    for pk, subject in enumerate(subjects, start=1):
        entry = SimpleNamespace(
            pk=pk,
            finding=SimpleNamespace(subject=subject),
            effective_value=f"Approved source value for {subject}",
        )
        for item in scope_items_for_entry(entry):
            counts[item.trade.label] += 1

    assert counts == {
        "General Requirements": 10,
        "Demolition": 5,
        "Environmental / Hazardous Materials": 1,
        "Plumbing": 3,
        "Fire Protection / Sprinkler": 1,
        "Storefront / Architectural Millwork": 5,
        "Electrical": 5,
        "Low Voltage / Security / AV": 4,
        "Doors / Hardware": 1,
        "Specialty Equipment / Security Grilles": 1,
    }
    assert sum(counts.values()) == 36


@pytest.mark.parametrize("role", [Membership.Role.ADMIN, Membership.Role.ESTIMATOR_OPERATOR])
def test_admin_and_estimator_can_generate_edit_and_mark_ready(
    project, user, membership, approved_snapshot, role
):
    membership.role = role
    membership.save(update_fields=("role",))
    base = {"organization_slug": project.organization.slug, "project_pk": project.pk}
    response = client_for(user).post(
        reverse("scope-package-generate", kwargs=base),
        {
            "confirmed": True,
            "expected_plan_fingerprint": build_scope_coverage_preview(project)["plan_fingerprint"],
            "expected_project_information_version": approved_snapshot.version,
        },
        format="json",
    )
    assert response.status_code == 201
    package_id = ScopePackage.objects.get(lifecycle=ScopePackage.Lifecycle.ACTIVE).pk
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


def test_default_list_hides_superseded_generation_and_history_can_be_requested(
    project, user, membership, approved_snapshot
):
    legacy = ScopePackage.objects.create(
        organization=project.organization,
        project=project,
        source_snapshot=approved_snapshot,
        trade_key="legacy-mechanical",
        trade_category="Legacy Mechanical",
        generation_rule_version=1,
        created_by=user,
        updated_by=user,
    )
    legacy.current_version = ScopePackageVersion.objects.create(
        package=legacy,
        version=1,
        title="Historical human-edited scope",
        description="Preserve this content.",
        created_by=user,
    )
    legacy.save(update_fields=("current_version", "updated_at"))
    generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)
    legacy.refresh_from_db()

    url = reverse(
        "scope-package-list",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    current = client_for(user).get(url)
    history = client_for(user).get(url, {"include_history": "true"})

    assert current.status_code == 200
    assert len(current.data) == 1
    assert current.data[0]["lifecycle"] == ScopePackage.Lifecycle.ACTIVE
    assert current.data[0]["current_version"]["scope_items"][0]["sources"][0]["page_number"] == 1
    assert history.status_code == 200
    assert len(history.data) == 2
    assert legacy.lifecycle == ScopePackage.Lifecycle.SUPERSEDED
    assert legacy.current_version.description == "Preserve this content."


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


def test_company_contact_and_trade_capability_are_organization_scoped(organization, user):
    company = Company.objects.create(
        organization=organization,
        display_name="Pacific Mechanical Ltd.",
        website="https://www.pacific-mech.example/path",
        phone="(604) 555-0101",
        city="Vancouver",
        province="BC",
        created_by=user,
        updated_by=user,
    )
    Contact.objects.create(
        company=company, name="Pat Lee", title="Estimator", email="pat@example.com", is_primary=True
    )
    capability = TradeCapability.objects.create(
        company=company,
        trade_key="hvac-mechanical",
        keywords=["ductwork"],
        service_cities=["Vancouver"],
        province="BC",
    )
    assert company.domain == "pacific-mech.example"
    assert company.normalized_phone == "6045550101"
    assert capability.company.contacts.get().is_primary


def test_internal_network_is_searched_by_trade_and_service_area(organization, user):
    company = Company.objects.create(
        organization=organization,
        display_name="Internal HVAC",
        city="Vancouver",
        province="BC",
        created_by=user,
        updated_by=user,
    )
    TradeCapability.objects.create(
        company=company, trade_key="hvac-mechanical", service_cities=["Vancouver"], province="BC"
    )
    assert internal_companies(
        organization=organization, trade_key="hvac-mechanical", city="Vancouver", province="BC"
    ) == [company]
    assert (
        internal_companies(
            organization=organization, trade_key="plumbing", city="Vancouver", province="BC"
        )
        == []
    )


def test_dedupe_priority_and_ambiguous_name_do_not_merge(organization, user):
    known = Company.objects.create(
        organization=organization,
        display_name="Known Co",
        website="https://known.example",
        phone="6045550102",
        city="Burnaby",
        external_provider="fake",
        external_place_id="place-1",
        created_by=user,
        updated_by=user,
    )
    assert (
        dedupe_company(
            organization,
            ContractorResult("Different", "Elsewhere", "BC", external_place_id="place-1"),
            "fake",
        )
        == known
    )
    Company.objects.create(
        organization=organization,
        display_name="Ambiguous Co",
        city="Surrey",
        created_by=user,
        updated_by=user,
    )
    Company.objects.create(
        organization=organization,
        display_name="Ambiguous Co",
        city="Surrey",
        created_by=user,
        updated_by=user,
    )
    assert (
        dedupe_company(organization, ContractorResult("Ambiguous Co", "Surrey", "BC"), "fake")
        is None
    )


def test_every_canonical_contractor_trade_has_controlled_search_terms():
    choice_keys = {key for key, _label in TRADE_CHOICES}
    assert choice_keys == CONTRACTOR_ELIGIBLE_TRADE_KEYS == set(TRADE_QUERY_TERMS)
    assert len(choice_keys) == 27
    assert all(len(TRADE_QUERY_TERMS[key]) >= 2 for key in choice_keys)
    assert "general-requirements" not in choice_keys


def test_project_centered_rectangle_and_distance_are_mile_based():
    center = SearchCenter(48.38, -89.25, "Project site")
    rectangle = bounding_rectangle(center, BUSINESS_RADIUS_MILES)
    assert rectangle["low"]["latitude"] < center.latitude < rectangle["high"]["latitude"]
    assert rectangle["low"]["longitude"] < center.longitude < rectangle["high"]["longitude"]
    assert round(great_circle_miles(48.38, -89.25, 49.8951, -97.1384)) == 371


def test_fake_provider_remains_network_free():
    outcome = FakeContractorDiscoveryProvider().search(
        trade_key="plumbing",
        city="Vancouver",
        province="BC",
        center=SearchCenter(49.2827, -123.1207, "Vancouver, BC"),
        radius_miles=200,
        keywords=[],
    )
    assert len(outcome.results) == 1


def test_google_trade_query_construction_is_controlled():
    assert build_search_queries(
        trade_key="hvac-mechanical",
        city="Thunder Bay",
        province="Ontario",
        country="CA",
        keywords=["retail", "retail"],
    ) == [
        "commercial HVAC contractor retail Thunder Bay Ontario Canada",
        "mechanical contractor retail Thunder Bay Ontario Canada",
    ]
    assert (
        build_search_queries(
            trade_key="general-requirements",
            city="Thunder Bay",
            province="Ontario",
            country="Canada",
            keywords=[],
        )
        == []
    )


def test_google_place_mapping_uses_only_safe_discovery_fields():
    result = map_google_place(
        {
            "id": "google-place-1",
            "displayName": {"text": "Lakehead Mechanical"},
            "formattedAddress": "1 Example St, Thunder Bay, ON",
            "websiteUri": "https://lakehead.example",
            "nationalPhoneNumber": "(807) 555-0100",
            "primaryType": "plumber",
            "types": ["plumber", "point_of_interest"],
            "rating": 4.6,
            "userRatingCount": 38,
            "location": {"latitude": 48.4, "longitude": -89.2},
            "addressComponents": [
                {"longText": "Shuniah", "types": ["locality"]},
                {
                    "longText": "Ontario",
                    "shortText": "ON",
                    "types": ["administrative_area_level_1"],
                },
                {"longText": "P7A 1A1", "types": ["postal_code"]},
                {"longText": "Canada", "shortText": "CA", "types": ["country"]},
            ],
            "ignoredOversizedField": {"raw": "not persisted"},
        },
        city="Thunder Bay",
        province="Ontario",
        country="Canada",
        query="commercial plumber Thunder Bay Ontario Canada",
    )
    assert result.display_name == "Lakehead Mechanical"
    assert result.external_place_id == "google-place-1"
    assert result.address == "1 Example St, Thunder Bay, ON"
    assert (result.city, result.province, result.postal_code) == ("Shuniah", "ON", "P7A 1A1")
    assert (result.latitude, result.longitude) == (48.4, -89.2)
    assert result.metadata == {
        "query": "commercial plumber Thunder Bay Ontario Canada",
        "primary_type": "plumber",
        "types": ["plumber", "point_of_interest"],
        "rating": 4.6,
        "review_count": 38,
    }
    assert (
        map_google_place(
            {"id": "missing-name"},
            city="Thunder Bay",
            province="Ontario",
            country="Canada",
            query="query",
        )
        is None
    )


class GoogleResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_google_provider_posts_minimal_mask_and_maps_missing_optional_fields():
    requests = []

    def opener(request, *, timeout):
        requests.append((request, timeout))
        return GoogleResponse(
            {
                "places": [
                    {
                        "id": "place-1",
                        "displayName": {"text": "Safe Plumbing"},
                        "location": {"latitude": 48.38, "longitude": -89.25},
                    }
                ]
            }
        )

    outcome = GooglePlacesContractorDiscoveryProvider(
        api_key="test-key-not-a-real-secret", opener=opener
    ).search(
        trade_key="plumbing",
        city="Thunder Bay",
        province="Ontario",
        country="Canada",
        center=SearchCenter(48.38, -89.25, "Thunder Bay, ON"),
        radius_miles=200,
        keywords=[],
    )
    assert len(requests) == 2
    assert len(outcome.results) == 1
    assert outcome.results[0].phone == outcome.results[0].website == ""
    request, timeout = requests[0]
    assert request.full_url == "https://places.googleapis.com/v1/places:searchText"
    assert timeout == 30
    assert request.get_header("X-goog-fieldmask") is not None
    assert "textQuery" in json.loads(request.data)


def test_google_provider_failure_is_safe_and_does_not_expose_key():
    def opener(*args, **kwargs):
        raise urllib.error.HTTPError("safe-url", 403, "forbidden", {}, None)

    provider = GooglePlacesContractorDiscoveryProvider(
        api_key="test-key-not-a-real-secret", opener=opener
    )
    with pytest.raises(ContractorProviderError) as error:
        provider.search(
            trade_key="plumbing",
            city="Thunder Bay",
            province="Ontario",
            country="Canada",
            center=SearchCenter(48.38, -89.25, "Thunder Bay, ON"),
            radius_miles=200,
            keywords=[],
        )
    assert str(error.value) == "Google contractor search is temporarily unavailable."
    assert "test-key" not in str(error.value)


def test_google_provider_enforces_boundary_dedupe_and_request_caps(monkeypatch):
    requests = []

    def opener(request, *, timeout):
        requests.append(json.loads(request.data))
        return GoogleResponse(
            {
                "places": [
                    {
                        "id": "boundary",
                        "displayName": {"text": "Boundary Co"},
                        "location": {"latitude": 200, "longitude": 0},
                    },
                    {
                        "id": "outside",
                        "displayName": {"text": "Outside Co"},
                        "location": {"latitude": 200.1, "longitude": 0},
                    },
                ],
                "nextPageToken": "bounded-next-page",
            }
        )

    monkeypatch.setattr(
        "apps.contractors.providers.great_circle_miles",
        lambda _lat1, _lon1, lat2, _lon2: lat2,
    )
    outcome = GooglePlacesContractorDiscoveryProvider(
        api_key="test-key-not-a-real-secret", opener=opener
    ).search(
        trade_key="plumbing",
        city="Thunder Bay",
        province="Ontario",
        center=SearchCenter(0, 0, "Project site"),
        radius_miles=200,
        keywords=[],
    )
    assert len(requests) == GOOGLE_MAX_REQUESTS == 2 * GOOGLE_MAX_PAGES_PER_QUERY
    assert all("locationRestriction" in payload for payload in requests)
    assert all("circle" not in payload["locationRestriction"] for payload in requests)
    assert [result.external_place_id for result in outcome.results] == ["boundary"]
    assert outcome.results[0].distance_miles == 200
    assert outcome.metadata == {
        "provider_request_count": 4,
        "raw_result_count": 8,
        "outside_radius_filtered_count": 4,
        "deduplicated_count": 3,
        "partial_failure_count": 0,
    }


def test_google_provider_returns_safe_partial_results_after_later_request_failure():
    call_count = 0

    def opener(request, *, timeout):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise urllib.error.URLError("simulated provider interruption")
        return GoogleResponse(
            {
                "places": [
                    {
                        "id": "inside",
                        "displayName": {"text": "Available Contractor"},
                        "location": {"latitude": 48.38, "longitude": -89.25},
                    }
                ],
                "nextPageToken": "next",
            }
        )

    outcome = GooglePlacesContractorDiscoveryProvider(
        api_key="test-key-not-a-real-secret", opener=opener
    ).search(
        trade_key="plumbing",
        city="Thunder Bay",
        province="Ontario",
        center=SearchCenter(48.38, -89.25, "Project site"),
        radius_miles=200,
        keywords=[],
    )
    assert [result.external_place_id for result in outcome.results] == ["inside"]
    assert outcome.metadata["partial_failure_count"] == 2
    assert outcome.metadata["provider_request_count"] == 3


def test_google_provider_failure_maps_to_safe_api_response(
    project, user, membership, approved_snapshot, settings, monkeypatch
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "google_places"
    generated = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0]
    package = next(item for item in generated if item.trade_key != "general-requirements")
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()

    class FailingProvider:
        def resolve_center(self, **kwargs):
            return SearchCenter(48.4020957, -89.2441234, "Thunder Bay, ON")

        def search(self, **kwargs):
            raise ContractorProviderError("Contractor search is temporarily unavailable.")

    monkeypatch.setattr("apps.contractors.services.provider_for", lambda name: FailingProvider())
    response = client_for(user).post(
        reverse(
            "contractor-discovery-search",
            kwargs={
                "organization_slug": project.organization.slug,
                "project_pk": project.pk,
            },
        ),
        {
            "scope_package_id": package.pk,
            "keywords": [],
        },
        format="json",
    )
    assert response.status_code == 503
    assert response.data == {
        "code": "contractor_provider_unavailable",
        "detail": "Contractor search is temporarily unavailable.",
    }
    assert DiscoveryRequest.objects.count() == 0


def test_discovery_requires_ready_scope_and_is_idempotent(
    project, user, approved_snapshot, settings
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "fake"
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    with pytest.raises(ValidationError, match="Only Ready"):
        discover_contractors(project=project, package=package, actor=user)
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()
    first = discover_contractors(
        project=project,
        package=package,
        actor=user,
        keywords=["commercial"],
    )
    second = discover_contractors(
        project=project,
        package=package,
        actor=user,
        keywords=["commercial"],
    )
    assert first.result_count == second.result_count == 1
    assert ScopeContractorCandidate.objects.count() == 1
    assert DiscoveryRequest.objects.count() == 2


def test_project_location_prefers_site_address_and_center_is_reused(
    project, user, approved_snapshot, settings, monkeypatch
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "fake"
    project.site_address_line_1 = "100 Project Road"
    project.postal_zip_code = "P7A 1A1"
    project.save(update_fields=("site_address_line_1", "postal_zip_code"))
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()
    calls = []

    class Provider:
        def resolve_center(self, *, location_query):
            calls.append(location_query)
            return SearchCenter(48.38, -89.25, "100 Project Road")

        def search(self, **kwargs):
            return ContractorSearchOutcome(results=(), metadata={"provider_request_count": 0})

    monkeypatch.setattr("apps.contractors.services.provider_for", lambda name: Provider())
    discover_contractors(project=project, package=package, actor=user)
    discover_contractors(project=project, package=package, actor=user)
    assert calls == ["100 Project Road, Thunder Bay, Ontario, P7A 1A1, CA"]
    assert project_location_query(project).startswith("100 Project Road")
    first, second = DiscoveryRequest.objects.order_by("id")
    assert first.provider_metadata["project_center"]["cached"] is False
    assert second.provider_metadata["project_center"]["cached"] is True


def test_google_discovery_persists_mapped_identity_and_safe_search_history(
    project, user, approved_snapshot, settings, monkeypatch
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "google_places"
    generated = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0]
    package = next(item for item in generated if item.trade_key != "general-requirements")
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()

    class MockGoogleProvider:
        def resolve_center(self, **kwargs):
            return SearchCenter(48.4020957, -89.2441234, "Thunder Bay, ON")

        def search(self, **kwargs):
            assert kwargs["country"] == "CA"
            return ContractorSearchOutcome(
                results=(
                    ContractorResult(
                        display_name="Lakehead Mechanical",
                        city="Thunder Bay",
                        province="Ontario",
                        country="Canada",
                        address="1 Example St, Thunder Bay, ON",
                        website="https://lakehead.example",
                        external_place_id="google-place-1",
                        latitude=48.4000007,
                        longitude=-89.2000007,
                        metadata={"rating": 4.6, "review_count": 38},
                    ),
                ),
                metadata={
                    "provider_request_count": 2,
                    "raw_result_count": 1,
                    "outside_radius_filtered_count": 0,
                    "deduplicated_count": 0,
                },
            )

    monkeypatch.setattr("apps.contractors.services.provider_for", lambda name: MockGoogleProvider())
    request = discover_contractors(
        project=project,
        package=package,
        actor=user,
        keywords=["retail"],
    )
    company = Company.objects.get(external_place_id="google-place-1")
    assert request.provider == "google_places"
    assert request.search_terms[0].endswith("retail Thunder Bay Ontario Canada")
    assert request.radius_miles == 200
    assert request.scope_version_id == package.current_version_id
    assert request.provider_metadata["provider_request_count"] == 3
    assert request.provider_metadata["search_request_count"] == 2
    assert request.provider_metadata["geocode_request_count"] == 1
    assert request.provider_metadata["external_result_count"] == 1
    assert request.center_latitude == Decimal("48.402096")
    assert request.center_longitude == Decimal("-89.244123")
    assert company.address == "1 Example St, Thunder Bay, ON"
    assert company.latitude == Decimal("48.400001")
    assert company.longitude == Decimal("-89.200001")
    assert company.trade_capabilities.get().source_metadata == {
        "provider": "google_places",
        "rating": 4.6,
        "review_count": 38,
    }


def test_google_dedupe_backfills_missing_coordinates_without_replacing_valid_history(
    project, user, approved_snapshot, settings, monkeypatch
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "google_places"
    generated = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0]
    package = next(item for item in generated if item.trade_key != "general-requirements")
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()

    missing = Company.objects.create(
        organization=project.organization,
        display_name="Existing Missing Coordinates",
        website="https://missing-coordinates.example",
        source_type=Company.Source.DISCOVERED,
        created_by=user,
        updated_by=user,
    )
    valid = Company.objects.create(
        organization=project.organization,
        display_name="Existing Valid Coordinates",
        website="https://valid-coordinates.example",
        source_type=Company.Source.DISCOVERED,
        latitude=Decimal("48.123456"),
        longitude=Decimal("-89.123456"),
        created_by=user,
        updated_by=user,
    )
    for company in (missing, valid):
        TradeCapability.objects.create(
            company=company,
            trade_key=package.trade_key,
            source_type=Company.Source.DISCOVERED,
            source_metadata={"provider": "google_places", "rating": 4.0},
        )
    contact = Contact.objects.create(
        company=missing,
        name="Existing Contact",
        email="existing@example.test",
        is_primary=True,
    )
    candidate = ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        scope_version=package.current_version,
        company=missing,
        status=ScopeContractorCandidate.Status.SHORTLISTED,
        created_by=user,
        updated_by=user,
    )

    class MockGoogleProvider:
        def resolve_center(self, **kwargs):
            return SearchCenter(48.4020957, -89.2441234, "Thunder Bay, ON")

        def search(self, **kwargs):
            return ContractorSearchOutcome(
                results=(
                    ContractorResult(
                        display_name=missing.display_name,
                        city="Thunder Bay",
                        province="Ontario",
                        website=missing.website,
                        external_place_id="missing-place",
                        latitude=48.4442738,
                        longitude=-89.2059327,
                        metadata={"rating": 5.0, "review_count": 172, "distance_miles": 3.6},
                    ),
                    ContractorResult(
                        display_name=valid.display_name,
                        city="Thunder Bay",
                        province="Ontario",
                        website=valid.website,
                        external_place_id="valid-place",
                        latitude=49.9999999,
                        longitude=-88.9999999,
                        metadata={"rating": 4.5, "review_count": 80, "distance_miles": 8.1},
                    ),
                ),
                metadata={"provider_request_count": 1},
            )

    monkeypatch.setattr("apps.contractors.services.provider_for", lambda name: MockGoogleProvider())
    discover_contractors(project=project, package=package, actor=user)

    missing.refresh_from_db()
    valid.refresh_from_db()
    candidate.refresh_from_db()
    assert Company.objects.filter(organization=project.organization).count() == 2
    assert missing.latitude == Decimal("48.444274")
    assert missing.longitude == Decimal("-89.205933")
    assert missing.trade_capabilities.get().source_metadata["distance_miles"] == 3.6
    assert rank_candidate(candidate).distance_miles == 3.6
    assert valid.latitude == Decimal("48.123456")
    assert valid.longitude == Decimal("-89.123456")
    assert candidate.status == ScopeContractorCandidate.Status.SHORTLISTED
    assert Contact.objects.get(pk=contact.pk).email == "existing@example.test"
    assert (
        ScopeContractorCandidate.objects.filter(
            project=project, scope_version=package.current_version
        ).count()
        == 2
    )


def test_candidate_permissions_and_human_shortlist(
    project, user, membership, approved_snapshot, settings
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "fake"
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()
    discover_contractors(project=project, package=package, actor=user)
    candidate = ScopeContractorCandidate.objects.get()
    base = {
        "organization_slug": project.organization.slug,
        "project_pk": project.pk,
        "candidate_pk": candidate.pk,
    }
    url = reverse("contractor-candidate-status", kwargs=base)
    response = client_for(user).patch(url, {"status": "shortlisted"}, format="json")
    assert response.status_code == 200 and response.data["status"] == "shortlisted"
    response = client_for(user).patch(url, {"status": "candidate"}, format="json")
    assert response.status_code == 200 and response.data["status"] == "candidate"
    response = client_for(user).patch(url, {"status": "candidate"}, format="json")
    assert response.status_code == 200 and response.data["status"] == "candidate"
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    assert client_for(user).patch(url, {"status": "rejected"}, format="json").status_code == 403


def test_candidate_stays_bound_to_searched_ready_version_and_hides_after_new_draft(
    project, user, membership, approved_snapshot, settings
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "fake"
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    ready_version, _ = revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()
    discover_contractors(project=project, package=package, actor=user)
    candidate = ScopeContractorCandidate.objects.get()
    assert candidate.scope_version_id == ready_version.pk

    revise_scope_package(
        package=package,
        actor=user,
        values={"description": "Human-edited successor draft"},
        mark_ready=False,
    )
    package.refresh_from_db()
    assert candidate.scope_version_id == ready_version.pk
    response = client_for(user).get(
        reverse(
            "contractor-candidate-list",
            kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
        )
    )
    assert response.status_code == 200
    assert response.data == []
    with pytest.raises(ValidationError, match="Only Ready"):
        discover_contractors(project=project, package=package, actor=user)


def test_trade_coverage_uses_configured_shortlist_target_and_is_viewer_read_only(
    project, user, membership, approved_snapshot, settings
):
    settings.CONTRACTOR_MIN_SHORTLIST_TARGET = 3
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()
    for index, candidate_status in enumerate(
        [
            ScopeContractorCandidate.Status.SHORTLISTED,
            ScopeContractorCandidate.Status.SHORTLISTED,
            ScopeContractorCandidate.Status.CANDIDATE,
        ],
        start=1,
    ):
        company = Company.objects.create(
            organization=project.organization,
            display_name=f"Coverage Contractor {index}",
            source_type=Company.Source.INTERNAL,
            created_by=user,
            updated_by=user,
        )
        ScopeContractorCandidate.objects.create(
            project=project,
            scope_package=package,
            company=company,
            status=candidate_status,
            created_by=user,
            updated_by=user,
        )
    url = reverse(
        "contractor-trade-coverage",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    response = client_for(user).get(url)
    assert response.status_code == 200
    assert response.data == {
        "minimum_shortlist_target": 3,
        "trades": [
            {
                "scope_package": package.pk,
                "trade_key": package.trade_key,
                "trade_category": package.trade_category,
                "title": package.current_version.title,
                "candidates_found": 3,
                "shortlisted_count": 2,
                "coverage_status": "needs_more_candidates",
            }
        ],
    }
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    assert client_for(user).get(url).status_code == 200
    assert client_for(user).post(url, {}, format="json").status_code == 405

    ScopeContractorCandidate.objects.filter(
        project=project, scope_package=package, status=ScopeContractorCandidate.Status.CANDIDATE
    ).update(status=ScopeContractorCandidate.Status.SHORTLISTED)
    response = client_for(user).get(url)
    assert response.data["trades"][0]["shortlisted_count"] == 3
    assert response.data["trades"][0]["coverage_status"] == "ready"


def test_contractor_profile_contact_management_readiness_and_permissions(
    project, user, membership, approved_snapshot
):
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()
    company = Company.objects.create(
        organization=project.organization,
        display_name="Provider Sourced Mechanical",
        website="https://provider.example",
        phone="807-555-0100",
        address="1 Provider Way",
        city="Thunder Bay",
        province="Ontario",
        source_type=Company.Source.DISCOVERED,
        external_provider="google_places",
        external_place_id="profile-google-1",
        created_by=user,
        updated_by=user,
    )
    TradeCapability.objects.create(
        company=company,
        trade_key=package.trade_key,
        source_type=Company.Source.DISCOVERED,
        source_metadata={"rating": 4.7, "review_count": 91},
    )
    candidate = ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        company=company,
        status=ScopeContractorCandidate.Status.SHORTLISTED,
        created_by=user,
        updated_by=user,
    )
    profile_url = reverse(
        "contractor-company-profile",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "company_pk": company.pk,
        },
    )
    contacts_url = reverse(
        "contractor-contact-list",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "company_pk": company.pk,
        },
    )
    profile = client_for(user).get(profile_url)
    assert profile.status_code == 200
    assert profile.data["contact_ready"] is False
    assert profile.data["google_rating"] == 4.7
    assert profile.data["google_review_count"] == 91
    assert profile.data["shortlist_statuses"] == [
        {
            "scope_package": package.pk,
            "trade_category": package.trade_category,
            "status": "shortlisted",
        }
    ]

    original_company = (company.display_name, company.website, company.phone, company.address)
    first_response = client_for(user).post(
        contacts_url,
        {
            "name": "Alex Estimator",
            "title": "Estimator",
            "email": "alex@example.com",
            "phone": "",
            "is_primary": True,
            "is_active": True,
        },
        format="json",
    )
    assert first_response.status_code == 201
    first = Contact.objects.get(pk=first_response.data["id"])
    assert client_for(user).get(profile_url).data["contact_ready"] is True

    second_response = client_for(user).post(
        contacts_url,
        {
            "name": "Morgan Manager",
            "title": "Project Manager",
            "phone": "807-555-0111",
            "is_primary": True,
            "is_active": True,
        },
        format="json",
    )
    assert second_response.status_code == 201
    first.refresh_from_db()
    assert first.is_primary is False
    second_id = second_response.data["id"]
    detail_url = reverse(
        "contractor-contact-detail",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "company_pk": company.pk,
            "contact_pk": second_id,
        },
    )
    update_response = client_for(user).patch(
        detail_url, {"title": "Senior Project Manager"}, format="json"
    )
    assert update_response.status_code == 200
    assert update_response.data["title"] == "Senior Project Manager"
    deactivate_response = client_for(user).patch(detail_url, {"is_active": False}, format="json")
    assert deactivate_response.status_code == 200
    assert deactivate_response.data["is_primary"] is False
    assert client_for(user).get(profile_url).data["contact_ready"] is False
    assert client_for(user).delete(detail_url).status_code == 405

    company.refresh_from_db()
    candidate.refresh_from_db()
    assert (
        company.display_name,
        company.website,
        company.phone,
        company.address,
    ) == original_company
    assert candidate.status == ScopeContractorCandidate.Status.SHORTLISTED
    assert AuditEvent.objects.filter(action_code="contractor_contact.created").count() == 2
    assert AuditEvent.objects.filter(action_code="contractor_contact.updated").count() == 1
    assert AuditEvent.objects.filter(action_code="contractor_contact.deactivated").count() == 1
    assert (
        not AuditEvent.objects.filter(action_code__startswith="contractor_contact.")
        .exclude(project=project)
        .exists()
    )
    assert not AuditEvent.objects.filter(action_code__contains="outreach").exists()

    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    assert client_for(user).get(profile_url).status_code == 200
    assert client_for(user).get(contacts_url).status_code == 200
    assert client_for(user).post(contacts_url, {"name": "Denied"}, format="json").status_code == 403
    assert client_for(user).patch(detail_url, {"is_active": True}, format="json").status_code == 403


def test_google_candidate_list_hides_fake_history_but_keeps_internal_and_google(
    project, user, membership, approved_snapshot, settings
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "google_places"
    generated = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0]
    package = next(item for item in generated if item.trade_key != "general-requirements")
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()
    companies = [
        Company.objects.create(
            organization=project.organization,
            display_name="Internal Network Co",
            source_type=Company.Source.INTERNAL,
            created_by=user,
            updated_by=user,
        ),
        Company.objects.create(
            organization=project.organization,
            display_name="Historical Fake Co",
            source_type=Company.Source.DISCOVERED,
            external_provider="fake",
            external_place_id="fake-history-1",
            created_by=user,
            updated_by=user,
        ),
        Company.objects.create(
            organization=project.organization,
            display_name="Google Places Co",
            source_type=Company.Source.DISCOVERED,
            external_provider="google_places",
            external_place_id="google-live-1",
            created_by=user,
            updated_by=user,
        ),
    ]
    for company in companies:
        ScopeContractorCandidate.objects.create(
            project=project,
            scope_package=package,
            company=company,
            created_by=user,
            updated_by=user,
        )
    response = client_for(user).get(
        reverse(
            "contractor-candidate-list",
            kwargs={
                "organization_slug": project.organization.slug,
                "project_pk": project.pk,
            },
        )
    )
    assert response.status_code == 200
    assert {item["company"]["display_name"] for item in response.data} == {
        "Internal Network Co",
        "Google Places Co",
    }
    assert Company.objects.filter(external_provider="fake").count() == 1
    assert ScopeContractorCandidate.objects.filter(company__external_provider="fake").count() == 1


def test_candidate_ranking_is_deterministic_and_transparent(project, user, approved_snapshot):
    project.city = "Thunder Bay"
    project.save(update_fields=("city", "updated_at"))
    generated = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0]
    package = next(item for item in generated if item.trade_key != "general-requirements")
    internal = Company.objects.create(
        organization=project.organization,
        display_name="Known Internal Contractor",
        source_type=Company.Source.INTERNAL,
        created_by=user,
        updated_by=user,
    )
    external = Company.objects.create(
        organization=project.organization,
        display_name="Strong Local Google Contractor",
        city=project.city,
        website="https://strong-local.example",
        phone="807-555-0100",
        source_type=Company.Source.DISCOVERED,
        external_provider="google_places",
        external_place_id="ranking-google-1",
        created_by=user,
        updated_by=user,
    )
    TradeCapability.objects.create(company=internal, trade_key=package.trade_key)
    TradeCapability.objects.create(
        company=external,
        trade_key=package.trade_key,
        source_type=Company.Source.DISCOVERED,
        source_metadata={"rating": 4.8, "review_count": 140},
    )
    internal_candidate = ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        company=internal,
        created_by=user,
        updated_by=user,
    )
    external_candidate = ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        company=external,
        created_by=user,
        updated_by=user,
    )
    internal_rank = rank_candidate(internal_candidate)
    external_rank = rank_candidate(external_candidate)
    assert internal_rank.score == 48
    assert internal_rank.reasons == ("Exact trade match", "Internal network")
    assert external_rank.score == 82
    assert external_rank.reasons == (
        "Exact trade match",
        "Local to project",
        "Website available",
        "Phone available",
        "Strong Google rating",
        "Established review history",
    )
    assert external_rank.score > internal_rank.score
    assert rank_candidate(external_candidate) == external_rank


def test_missing_google_quality_is_neutral_and_shortlist_is_additive(
    project, user, approved_snapshot
):
    generated = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0]
    package = next(item for item in generated if item.trade_key != "general-requirements")
    company = Company.objects.create(
        organization=project.organization,
        display_name="Unrated External Contractor",
        source_type=Company.Source.DISCOVERED,
        external_provider="google_places",
        external_place_id="ranking-google-unrated",
        created_by=user,
        updated_by=user,
    )
    TradeCapability.objects.create(
        company=company,
        trade_key=package.trade_key,
        source_type=Company.Source.DISCOVERED,
        source_metadata={},
    )
    candidate = ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        company=company,
        created_by=user,
        updated_by=user,
    )
    unranked = rank_candidate(candidate)
    assert unranked.score == 30
    assert unranked.google_rating is None
    assert unranked.google_review_count is None
    assert all("rating" not in reason.casefold() for reason in unranked.reasons)
    candidate.status = ScopeContractorCandidate.Status.SHORTLISTED
    shortlisted = rank_candidate(candidate)
    assert shortlisted.score == 35
    assert "Shortlisted by BB Builders" in shortlisted.reasons


def test_candidate_ranking_caps_at_100_and_explains_lower_quality_tiers(
    project, user, approved_snapshot
):
    project.city = "Thunder Bay"
    project.save(update_fields=("city", "updated_at"))
    generated = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0]
    package = next(item for item in generated if item.trade_key != "general-requirements")
    company = Company.objects.create(
        organization=project.organization,
        display_name="Fully Scored Contractor",
        city=project.city,
        website="https://fully-scored.example",
        phone="807-555-0199",
        source_type=Company.Source.INTERNAL,
        created_by=user,
        updated_by=user,
    )
    TradeCapability.objects.create(
        company=company,
        trade_key=package.trade_key,
        source_type=Company.Source.DISCOVERED,
        source_metadata={"rating": 3.6, "review_count": 8},
    )
    candidate = ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        company=company,
        status=ScopeContractorCandidate.Status.SHORTLISTED,
        created_by=user,
        updated_by=user,
    )
    ranking = rank_candidate(candidate)
    assert ranking.score == 90
    assert "Google rating signal" in ranking.reasons
    assert "Review history available" in ranking.reasons

    capability = company.trade_capabilities.get(trade_key=package.trade_key)
    capability.source_metadata = {"rating": 5.0, "review_count": 500}
    capability.save(update_fields=("source_metadata", "updated_at"))
    assert rank_candidate(candidate).score == 100


def test_contact_enrichment_prefills_from_limited_public_pages_without_saving(
    project, user, approved_snapshot, settings, monkeypatch
):
    settings.CONTACT_ENRICHMENT_MAX_PAGES = 4
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    company = Company.objects.create(
        organization=project.organization,
        display_name="Public Mechanical",
        website="https://public.example",
        source_type=Company.Source.DISCOVERED,
        external_provider="google_places",
        created_by=user,
        updated_by=user,
    )
    ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        company=company,
        created_by=user,
        updated_by=user,
    )
    pages = {
        "https://public.example": (
            "https://public.example",
            '<a href="/contact">Contact</a>',
        ),
        "https://public.example/contact": (
            "https://public.example/contact",
            '<a href="mailto:bids@public.example">Taylor Smith</a>'
            '<a href="tel:+1-807-555-0102">Call estimating</a>',
        ),
    }
    monkeypatch.setattr(
        "apps.contractors.enrichment._safe_public_url", lambda *args, **kwargs: True
    )
    result = enrich_company_contacts(company, fetcher=lambda url: pages.get(url))
    assert Contact.objects.filter(company=company).count() == 0
    assert result["pages_checked"] == ["https://public.example", "https://public.example/contact"]
    assert result["suggestions"] == [
        {
            "name": "Taylor Smith",
            "title": "",
            "email": "bids@public.example",
            "phone": "+1-807-555-0102",
            "is_primary": True,
            "is_active": True,
            "sources": [
                {
                    "label": "Contact page",
                    "url": "https://public.example/contact",
                    "fields": ["email", "phone", "name"],
                }
            ],
        }
    ]


def test_contact_enrichment_no_result_and_viewer_cannot_request_it(
    project, user, membership, approved_snapshot, monkeypatch
):
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    company = Company.objects.create(
        organization=project.organization,
        display_name="No Public Contact Co",
        website="https://no-contact.example",
        source_type=Company.Source.DISCOVERED,
        external_provider="google_places",
        created_by=user,
        updated_by=user,
    )
    ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        company=company,
        created_by=user,
        updated_by=user,
    )
    monkeypatch.setattr(
        "apps.contractors.views.enrich_company_contacts",
        lambda company: {"suggestions": [], "pages_checked": [company.website]},
    )
    url = reverse(
        "contractor-contact-enrichment",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "company_pk": company.pk,
        },
    )
    response = client_for(user).post(url, {}, format="json")
    assert response.status_code == 200
    assert response.data["suggestions"] == []
    assert Contact.objects.filter(company=company).count() == 0
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    assert client_for(user).post(url, {}, format="json").status_code == 403


def test_confirming_same_suggested_contact_is_idempotent(project, user):
    company = Company.objects.create(
        organization=project.organization,
        display_name="Duplicate Safe Co",
        created_by=user,
        updated_by=user,
    )
    values = {
        "name": "Alex Estimator",
        "title": "Estimator",
        "email": "estimating@example.com",
        "phone": "807-555-0100",
        "is_primary": True,
        "is_active": True,
    }
    first, first_created = create_contact(
        company=company, project=project, actor=user, values=values
    )
    second, second_created = create_contact(
        company=company,
        project=project,
        actor=user,
        values={**values, "email": "ESTIMATING@example.com"},
    )
    assert first_created is True
    assert second_created is False
    assert second.pk == first.pk
    assert Contact.objects.filter(company=company).count() == 1
    assert AuditEvent.objects.filter(action_code="contractor_contact.created").count() == 1
