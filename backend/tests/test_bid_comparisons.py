"""M3-08 deterministic leveling over explicitly selected Ready bids."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.contractors.models import Company, Contact, ScopeContractorCandidate
from apps.organizations.models import Membership, Organization
from apps.outreach.bid_intake import record_manual_quote
from apps.outreach.bid_revisions import create_revision
from apps.outreach.comparisons import (
    add_entry,
    create_comparison,
    detail_data,
    detail_queryset,
    evaluated_amount,
    mark_comparison_ready,
    save_adjustment,
)
from apps.outreach.models import (
    BidCommercialItem,
    BidComparison,
    BidEvidence,
    BidRevision,
    InvitationCampaign,
)
from apps.outreach.services import add_invitation_recipient, create_invitation_batch
from apps.projects.models import Project
from apps.scope_packages.models import ScopeItem

from .test_bid_intake import storage as intake_storage
from .test_outreach import setup as outreach_setup
from .test_outreach_responses import fixture_outreach

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n% synthetic comparison quote\n%%EOF\n"


@pytest.fixture
def setup(user, organization, membership):
    return outreach_setup.__wrapped__(user, organization, membership)


@pytest.fixture
def storage(monkeypatch):
    return intake_storage.__wrapped__(monkeypatch)


def ready_revision(
    setup, user, *, second=False, amount="100000.00", currency="CAD", source_terms=False
):
    if second:
        project, package, version, _, _ = setup
        company = Company.objects.create(
            organization=project.organization,
            display_name="Second Mechanical",
            created_by=user,
            updated_by=user,
        )
        contact = Contact.objects.create(
            company=company, name="Second Estimator", email="second@example.invalid"
        )
        candidate = ScopeContractorCandidate.objects.create(
            project=project,
            scope_package=package,
            scope_version=version,
            company=company,
            status=ScopeContractorCandidate.Status.APPROVED,
            created_by=user,
            updated_by=user,
        )
        campaign = InvitationCampaign.objects.get(project=project, scope_version=version)
        batch = create_invitation_batch(campaign=campaign, actor=user)
        recipient = add_invitation_recipient(
            batch=batch, candidate=candidate, contact=contact, actor=user
        )
        type(recipient).objects.filter(pk=recipient.pk).update(current_status="invited")
        recipient.refresh_from_db()
    else:
        project, recipient, _ = fixture_outreach(setup, user)
    submission = record_manual_quote(
        recipient=recipient,
        actor=user,
        files=[SimpleUploadedFile("quote.pdf", PDF, content_type="application/pdf")],
        received_at=timezone.now(),
    )
    revision = create_revision(submission=submission, actor=user)
    if source_terms:
        BidCommercialItem.objects.create(
            revision=revision,
            sequence=1,
            kind="alternate",
            title="Source alternate",
            treatment="add",
            amount=Decimal("9999.00"),
            currency=currency,
        )
        BidCommercialItem.objects.create(
            revision=revision,
            sequence=2,
            kind="allowance",
            title="Source allowance",
            amount=Decimal("5000.00"),
            currency=currency,
            included_in_base="yes",
        )
    BidRevision.objects.filter(pk=revision.pk).update(
        status="ready",
        base_bid=amount,
        base_bid_review="confirmed",
        currency=currency,
        currency_review="confirmed",
        tax_reviewed=True,
        commercial_items_reviewed=True,
        scope_reviewed=True,
        reviewed_by=user,
        reviewed_at=timezone.now(),
    )
    return BidRevision.objects.get(pk=revision.pk)


def test_explicit_ready_selection_exact_scope_and_no_automatic_latest(setup, user, storage):
    first = ready_revision(setup, user)
    draft = create_revision(submission=first.submission, actor=user)
    comparison = create_comparison(
        project=first.project, scope_version=first.scope_version, actor=user
    )
    assert comparison.entries.count() == 0
    with pytest.raises(ValidationError):
        add_entry(comparison=comparison, revision=draft, actor=user)
    entry = add_entry(comparison=comparison, revision=first, actor=user)
    assert entry.revision_id == first.pk
    assert entry.company_name == first.company.display_name
    with pytest.raises(ValidationError):
        add_entry(comparison=comparison, revision=first, actor=user)
    wrong_project = Project.objects.create(
        organization=first.organization,
        created_by=user,
        project_number="WRONG-1",
        name="Wrong project",
    )
    with pytest.raises(ValidationError):
        create_comparison(project=wrong_project, scope_version=first.scope_version, actor=user)


def test_project_api_creates_empty_comparison_then_explicitly_adds_revision(setup, user, storage):
    revision = ready_revision(setup, user)
    client = APIClient()
    client.force_authenticate(user=user)
    list_url = reverse(
        "bid-comparison-list",
        kwargs={
            "organization_slug": revision.organization.slug,
            "project_pk": revision.project_id,
        },
    )
    created = client.post(list_url, {"scope_version_id": revision.scope_version_id}, format="json")
    assert created.status_code == 201
    assert created.data["entries"] == []
    entry_url = reverse(
        "bid-comparison-entry-list",
        kwargs={
            "organization_slug": revision.organization.slug,
            "project_pk": revision.project_id,
            "comparison_pk": created.data["id"],
        },
    )
    added = client.post(entry_url, {"revision_id": revision.pk}, format="json")
    assert added.status_code == 201
    assert added.data["entries"][0]["revision_id"] == revision.pk


def test_decimal_leveling_is_explicit_and_source_terms_do_not_change_total(setup, user, storage):
    revision = ready_revision(setup, user, amount="176500.00", source_terms=True)
    comparison = create_comparison(
        project=revision.project, scope_version=revision.scope_version, actor=user
    )
    entry = add_entry(comparison=comparison, revision=revision, actor=user)
    add = save_adjustment(
        entry=entry,
        actor=user,
        values={
            "direction": "add",
            "amount": "7000.00",
            "currency": "CAD",
            "category": "scope_gap",
            "description": "Explicit estimator scope leveling",
        },
    )
    save_adjustment(
        entry=entry,
        actor=user,
        values={
            "direction": "deduct",
            "amount": "1000.00",
            "currency": "CAD",
            "category": "other",
            "description": "Explicit estimator deduction",
        },
    )
    assert add.amount == Decimal("7000.00")
    entry = type(entry).objects.prefetch_related("adjustments").get(pk=entry.pk)
    assert evaluated_amount(entry) == Decimal("182500.00")
    assert revision.base_bid == Decimal("176500.00")
    assert revision.commercial_items.count() == 2  # Source terms are visible but never auto-added.


def test_condition_detail_is_grounded_in_exact_evidence_without_rewriting_ready_bid(
    setup, user, storage
):
    revision = ready_revision(setup, user)
    BidRevision.objects.filter(pk=revision.pk).update(status="draft")
    revision.refresh_from_db()
    lead_time = BidCommercialItem.objects.create(
        revision=revision,
        sequence=1,
        kind="condition",
        title="Equipment lead time",
        description="Equipment lead time",
        treatment="not_stated",
    )
    BidEvidence.objects.bulk_create(
        [
            BidEvidence(
                revision=revision,
                attachment=revision.submission.attachments.first(),
                commercial_item=lead_time,
                source="quote",
                page_number=1,
                excerpt="Qualification:\nEquipment lead time is 14 weeks.",
            )
        ]
    )
    generic = BidCommercialItem.objects.create(
        revision=revision,
        sequence=2,
        kind="condition",
        title="General qualification",
        description="General qualification",
    )
    BidRevision.objects.filter(pk=revision.pk).update(status="ready")
    revision.refresh_from_db()
    comparison = create_comparison(
        project=revision.project, scope_version=revision.scope_version, actor=user
    )
    add_entry(comparison=comparison, revision=revision, actor=user)

    items = detail_data(detail_queryset(revision.project).get(pk=comparison.pk))["entries"][0][
        "commercial_items"
    ]
    assert items[0]["detail"] == "14 weeks"
    assert items[0]["evidence"][0]["excerpt"].endswith("14 weeks.")
    assert items[1]["detail"] == ""
    revision.refresh_from_db()
    assert revision.status == "ready"
    assert generic.description == "General qualification"


def test_scope_matrix_preserves_missing_as_not_addressed_and_ready_freezes(setup, user, storage):
    first = ready_revision(setup, user)
    second = ready_revision(setup, user, second=True, amount="110000.00")
    item = ScopeItem.objects.create(
        package_version=first.scope_version,
        item_key="ductwork",
        item_type="supply_install",
        responsibility="supply_install",
        title="Ductwork",
        description="Supply and install ductwork",
        sequence=1,
    )
    comparison = create_comparison(
        project=first.project, scope_version=first.scope_version, actor=user
    )
    add_entry(comparison=comparison, revision=first, actor=user)
    add_entry(comparison=comparison, revision=second, actor=user)
    data = detail_data(detail_queryset(first.project).get(pk=comparison.pk))
    assert all(
        row["coverage"][str(item.pk)]
        == {"state": "not_addressed", "recorded": False, "wording": ""}
        for row in data["entries"]
    )
    assert data["currency_comparable"] is True
    ready = mark_comparison_ready(comparison=comparison, actor=user)
    assert ready.status == "ready"
    with pytest.raises(ValidationError):
        add_entry(comparison=ready, revision=first, actor=user)


def test_different_or_missing_currency_blocks_cross_bid_price_comparison(setup, user, storage):
    first = ready_revision(setup, user, currency="CAD")
    second = ready_revision(setup, user, second=True, currency="USD")
    comparison = create_comparison(
        project=first.project, scope_version=first.scope_version, actor=user
    )
    add_entry(comparison=comparison, revision=first, actor=user)
    add_entry(comparison=comparison, revision=second, actor=user)
    assert (
        detail_data(detail_queryset(first.project).get(pk=comparison.pk))["currency_comparable"]
        is False
    )

    BidRevision.objects.filter(pk=first.pk).update(
        base_bid=None, base_bid_review="not_stated", currency="", currency_review="not_stated"
    )
    first.refresh_from_db()
    first_entry = comparison.entries.get(revision=first)
    first_entry = type(first_entry).objects.prefetch_related("adjustments").get(pk=first_entry.pk)
    assert evaluated_amount(first_entry) is None


def test_viewer_can_read_but_cannot_create_comparison(setup, user, membership, storage):
    revision = ready_revision(setup, user)
    membership.role = Membership.Role.VIEWER
    membership.save()
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse(
        "bid-comparison-list",
        kwargs={
            "organization_slug": revision.organization.slug,
            "project_pk": revision.project_id,
        },
    )
    assert client.get(url).status_code == 200
    assert (
        client.post(url, {"scope_version_id": revision.scope_version_id}, format="json").status_code
        == 403
    )
    assert BidComparison.objects.count() == 0


def test_inactive_and_cross_organization_access_are_denied(setup, user, membership, storage):
    revision = ready_revision(setup, user)
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse(
        "bid-comparison-list",
        kwargs={
            "organization_slug": revision.organization.slug,
            "project_pk": revision.project_id,
        },
    )
    membership.is_active = False
    membership.save()
    assert client.get(url).status_code == 403
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    Membership.objects.create(
        organization=other, user=user, role=Membership.Role.ESTIMATOR_OPERATOR
    )
    cross_url = reverse(
        "bid-comparison-list",
        kwargs={"organization_slug": other.slug, "project_pk": revision.project_id},
    )
    assert client.get(cross_url).status_code == 404
