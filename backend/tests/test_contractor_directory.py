import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.analysis.models import ProjectIntelligenceSnapshot
from apps.contractors.models import Company, Contact, ScopeContractorCandidate, TradeCapability
from apps.organizations.models import Membership, Organization
from apps.projects.models import Project
from apps.scope_packages.models import ScopePackage, ScopePackageVersion

pytestmark = pytest.mark.django_db


def company(organization, user, name="North Mechanical", **values):
    return Company.objects.create(
        organization=organization,
        display_name=name,
        created_by=user,
        updated_by=user,
        **values,
    )


def authenticated(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def directory_url(organization):
    return reverse(
        "contractor-company-directory",
        kwargs={"organization_slug": organization.slug},
    )


def test_directory_is_organization_scoped_searchable_filterable_and_viewer_readable(
    organization, user, membership
):
    target = company(
        organization,
        user,
        legal_name="North Mechanical Incorporated",
        city="Thunder Bay",
        province="Ontario",
        source_type=Company.Source.INTERNAL,
    )
    Contact.objects.create(
        company=target,
        name="Pat Estimator",
        email="pat@example.com",
        is_primary=True,
    )
    TradeCapability.objects.create(
        company=target,
        trade_key="hvac-mechanical",
        service_cities=["Thunder Bay"],
        province="Ontario",
    )
    company(organization, user, name="Inactive Plumbing", is_active=False)
    fake = company(
        organization,
        user,
        name="Fake Provider Demo",
        source_type=Company.Source.DISCOVERED,
        external_provider="fake",
    )
    other = Organization.objects.create(name="Other", slug="other")
    company(other, user, name="Other Organization")
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=["role"])

    response = authenticated(user).get(
        directory_url(organization),
        {"search": "Pat", "trade": "hvac-mechanical", "active": "true"},
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == target.pk
    assert response.data["results"][0]["usable_contact_count"] == 1
    assert response.data["results"][0]["primary_email_ready"] is True
    assert response.data["summary"] == {
        "total": 2,
        "active": 1,
        "contact_ready": 1,
        "trades_covered": 1,
    }
    assert fake.pk not in [item["id"] for item in response.data["results"]]
    assert response.data["filters"]["cities"] == ["Thunder Bay"]


def test_directory_paginates_and_supports_contact_readiness(organization, user, membership):
    for index in range(3):
        item = company(organization, user, name=f"Company {index}")
        if index == 0:
            Contact.objects.create(company=item, name="Phone Contact", phone="555-0100")
    response = authenticated(user).get(
        directory_url(organization), {"page_size": 2, "contact_ready": "false"}
    )
    assert response.status_code == 200
    assert response.data["count"] == 2
    assert len(response.data["results"]) == 2
    assert response.data["page_size"] == 2


def test_company_detail_returns_bounded_contextual_history_and_denies_cross_org(
    organization, user, membership
):
    target = company(organization, user)
    Contact.objects.create(company=target, name="Primary", email="primary@example.com")
    TradeCapability.objects.create(company=target, trade_key="hvac-mechanical")
    project = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="DIR-1",
        name="Directory Project",
        project_timezone="America/Toronto",
    )
    snapshot = ProjectIntelligenceSnapshot.objects.create(
        project=project,
        version=1,
        fingerprint="a" * 64,
        manifest={"source": "directory-test"},
        summary_counts={"total": 1},
        created_by=user,
    )
    package = ScopePackage.objects.create(
        organization=organization,
        project=project,
        source_snapshot=snapshot,
        trade_key="hvac-mechanical",
        trade_category="HVAC / Mechanical",
        created_by=user,
        updated_by=user,
    )
    version = ScopePackageVersion.objects.create(
        package=package,
        version=1,
        title="HVAC",
        status=ScopePackageVersion.Status.READY,
        created_by=user,
    )
    package.current_version = version
    package.save(update_fields=["current_version", "updated_at"])
    ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        scope_version=version,
        company=target,
        status=ScopeContractorCandidate.Status.APPROVED,
        created_by=user,
        updated_by=user,
    )
    historical_package = ScopePackage.objects.create(
        organization=organization,
        project=project,
        source_snapshot=snapshot,
        trade_key="hvac-mechanical",
        trade_category="HVAC / Mechanical",
        generation_rule_version=2,
        lifecycle=ScopePackage.Lifecycle.SUPERSEDED,
        created_by=user,
        updated_by=user,
    )
    historical_version = ScopePackageVersion.objects.create(
        package=historical_package,
        version=1,
        title="Historical HVAC",
        status=ScopePackageVersion.Status.READY,
        created_by=user,
    )
    historical_package.current_version = historical_version
    historical_package.save(update_fields=["current_version", "updated_at"])
    ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=historical_package,
        scope_version=historical_version,
        company=target,
        created_by=user,
        updated_by=user,
    )
    plumbing_package = ScopePackage.objects.create(
        organization=organization,
        project=project,
        source_snapshot=snapshot,
        trade_key="plumbing",
        trade_category="Plumbing",
        created_by=user,
        updated_by=user,
    )
    plumbing_version = ScopePackageVersion.objects.create(
        package=plumbing_package,
        version=1,
        title="Plumbing",
        status=ScopePackageVersion.Status.READY,
        created_by=user,
    )
    plumbing_package.current_version = plumbing_version
    plumbing_package.save(update_fields=["current_version", "updated_at"])
    ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=plumbing_package,
        scope_version=plumbing_version,
        company=target,
        created_by=user,
        updated_by=user,
    )
    url = reverse(
        "contractor-company-directory-detail",
        kwargs={"organization_slug": organization.slug, "company_pk": target.pk},
    )
    response = authenticated(user).get(url)
    assert response.status_code == 200
    assert response.data["company"]["id"] == target.pk
    assert len(response.data["project_history"]) == 2
    hvac = next(
        item for item in response.data["project_history"] if item["trade_key"] == "hvac-mechanical"
    )
    assert hvac["scope_version_id"] == version.pk
    assert hvac["candidate_status"] == ScopeContractorCandidate.Status.APPROVED
    assert hvac["history_count"] == 2
    assert {item["scope_version_id"] for item in hvac["history"]} == {
        version.pk,
        historical_version.pk,
    }
    assert any(item["trade_key"] == "plumbing" for item in response.data["project_history"])
    assert response.data["outreach_history"] == []
    assert response.data["bid_history"] == []
    assert "not a universal" in response.data["history_note"]

    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(user=user, organization=other, role=Membership.Role.VIEWER)
    cross_org = authenticated(user).get(
        reverse(
            "contractor-company-directory-detail",
            kwargs={"organization_slug": other.slug, "company_pk": target.pk},
        )
    )
    assert cross_org.status_code == 404


def test_directory_requires_active_membership(organization, user):
    response = authenticated(user).get(directory_url(organization))
    assert response.status_code == 403


def test_directory_search_does_not_infer_global_qualification(organization, user, membership):
    target = company(organization, user)
    response = authenticated(user).get(directory_url(organization))
    assert response.status_code == 200
    item = next(item for item in response.data["results"] if item["id"] == target.pk)
    assert "qualification" not in item
