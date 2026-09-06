import hashlib
import json
import urllib.error
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
from apps.contractors.models import (
    Company,
    Contact,
    DiscoveryRequest,
    ScopeContractorCandidate,
    TradeCapability,
)
from apps.contractors.providers import (
    ContractorProviderError,
    ContractorResult,
    FakeContractorDiscoveryProvider,
    GooglePlacesContractorDiscoveryProvider,
    build_search_queries,
    map_google_place,
)
from apps.contractors.services import dedupe_company, discover_contractors, internal_companies
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


def test_fake_provider_remains_network_free():
    assert (
        len(
            FakeContractorDiscoveryProvider().search(
                trade_key="plumbing", city="Vancouver", province="BC", radius_km=50, keywords=[]
            )
        )
        == 1
    )


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
            {"places": [{"id": "place-1", "displayName": {"text": "Safe Plumbing"}}]}
        )

    results = GooglePlacesContractorDiscoveryProvider(
        api_key="test-key-not-a-real-secret", opener=opener
    ).search(
        trade_key="plumbing",
        city="Thunder Bay",
        province="Ontario",
        country="Canada",
        radius_km=50,
        keywords=[],
    )
    assert len(requests) == 2
    assert len(results) == 1
    assert results[0].phone == results[0].website == results[0].address == ""
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
            radius_km=None,
            keywords=[],
        )
    assert str(error.value) == "Contractor search is temporarily unavailable."
    assert "test-key" not in str(error.value)


def test_google_provider_failure_maps_to_safe_api_response(
    project, user, membership, approved_snapshot, settings, monkeypatch
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "google_places"
    generated = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0]
    package = next(item for item in generated if item.trade_key != "general-requirements")
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()

    class FailingProvider:
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
            "city": "Thunder Bay",
            "province": "Ontario",
            "country": "CA",
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
        discover_contractors(
            project=project, package=package, actor=user, city="Vancouver", province="BC"
        )
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()
    first = discover_contractors(
        project=project,
        package=package,
        actor=user,
        city="Vancouver",
        province="BC",
        keywords=["commercial"],
    )
    second = discover_contractors(
        project=project,
        package=package,
        actor=user,
        city="Vancouver",
        province="BC",
        keywords=["commercial"],
    )
    assert first.result_count == second.result_count == 1
    assert ScopeContractorCandidate.objects.count() == 1
    assert DiscoveryRequest.objects.count() == 2


def test_google_discovery_persists_mapped_identity_and_safe_search_history(
    project, user, approved_snapshot, settings, monkeypatch
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "google_places"
    generated = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0]
    package = next(item for item in generated if item.trade_key != "general-requirements")
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()

    class MockGoogleProvider:
        def search(self, **kwargs):
            assert kwargs["country"] == "CA"
            return [
                ContractorResult(
                    display_name="Lakehead Mechanical",
                    city="Thunder Bay",
                    province="Ontario",
                    country="Canada",
                    address="1 Example St, Thunder Bay, ON",
                    website="https://lakehead.example",
                    external_place_id="google-place-1",
                    metadata={"rating": 4.6, "review_count": 38},
                )
            ]

    monkeypatch.setattr("apps.contractors.services.provider_for", lambda name: MockGoogleProvider())
    request = discover_contractors(
        project=project,
        package=package,
        actor=user,
        city="Thunder Bay",
        province="Ontario",
        country="CA",
        keywords=["retail"],
    )
    company = Company.objects.get(external_place_id="google-place-1")
    assert request.provider == "google_places"
    assert request.search_terms[0].endswith("retail Thunder Bay Ontario Canada")
    assert request.provider_metadata == {
        "internal_first": True,
        "query_count": 2,
        "external_result_count": 1,
    }
    assert company.address == "1 Example St, Thunder Bay, ON"
    assert company.trade_capabilities.get().source_metadata == {
        "provider": "google_places",
        "rating": 4.6,
        "review_count": 38,
    }


def test_candidate_permissions_and_human_shortlist(
    project, user, membership, approved_snapshot, settings
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "fake"
    package = generate_scope_packages(project=project, snapshot=approved_snapshot, actor=user)[0][0]
    revise_scope_package(package=package, actor=user, values={}, mark_ready=True)
    package.refresh_from_db()
    discover_contractors(
        project=project, package=package, actor=user, city="Vancouver", province="BC"
    )
    candidate = ScopeContractorCandidate.objects.get()
    base = {
        "organization_slug": project.organization.slug,
        "project_pk": project.pk,
        "candidate_pk": candidate.pk,
    }
    url = reverse("contractor-candidate-status", kwargs=base)
    response = client_for(user).patch(url, {"status": "shortlisted"}, format="json")
    assert response.status_code == 200 and response.data["status"] == "shortlisted"
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    assert client_for(user).patch(url, {"status": "rejected"}, format="json").status_code == 403


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
