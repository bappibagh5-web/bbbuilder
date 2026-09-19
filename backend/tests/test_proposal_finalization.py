from datetime import date
from decimal import Decimal

import pymupdf
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership
from apps.proposals.commercial import (
    assemble_selected_reviews,
    save_allowance,
    save_exclusion,
    save_financial_adjustment,
)
from apps.proposals.lifecycle import finalize_proposal, update_draft_content
from apps.proposals.models import EstimateVersion, ProposalPdfArtifact, ProposalVersion
from apps.proposals.pdf import generate_final_pdf
from apps.proposals.services import create_estimate, create_estimate_version, create_proposal

from .test_bid_comparisons import storage as comparison_storage
from .test_document_uploads import FakeObjectStorage
from .test_estimate_financials import finalized_selection
from .test_outreach import setup as outreach_setup

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(user, organization, membership):
    return outreach_setup.__wrapped__(user, organization, membership)


@pytest.fixture
def storage(monkeypatch):
    return comparison_storage.__wrapped__(monkeypatch)


def prepared(setup, user, storage):
    review, _, _ = finalized_selection(setup, user, storage)
    project = review.project
    project.client_name = "Client Company"
    project.site_address_line_1 = "100 Main Street"
    project.save(update_fields=["client_name", "site_address_line_1"])
    estimate, estimate_version = create_estimate(project=project, actor=user)
    assemble_selected_reviews(version=estimate_version, review_ids=[review.pk], actor=user)
    save_allowance(
        version=estimate_version,
        actor=user,
        data={
            "description": "Controls allowance",
            "amount": Decimal("5000"),
            "currency": "CAD",
            "treatment": "included",
        },
    )
    save_exclusion(
        version=estimate_version, actor=user, data={"description": "Electrical by others"}
    )
    save_financial_adjustment(
        version=estimate_version,
        actor=user,
        data={
            "category": "tax",
            "description": "HST",
            "method": "percentage",
            "basis": "pre_tax_subtotal",
            "percentage_rate": Decimal("5"),
            "currency": "CAD",
        },
    )
    proposal, proposal_version = create_proposal(
        estimate=estimate, estimate_version=estimate_version, actor=user
    )
    update_draft_content(
        version=proposal_version,
        actor=user,
        data={
            "issue_date": date(2026, 9, 19),
            "scope_summary": "Construct the approved project scope.",
            "commercial_notes": "Pricing remains valid as stated.",
        },
    )
    return project, estimate, estimate_version, proposal, proposal_version


def test_finalize_freezes_exact_versions_and_preserves_snapshots(setup, user, storage):
    project, _, estimate, _, proposal = prepared(setup, user, storage)
    assert proposal.client_contact_id is None
    finalized = finalize_proposal(version=proposal, actor=user)
    estimate.refresh_from_db()
    assert finalized.status == ProposalVersion.Status.FINALIZED
    assert estimate.status == EstimateVersion.Status.FROZEN
    assert finalized.commercial_snapshot["currency"] == "CAD"
    assert finalized.commercial_snapshot["total_amount"] == "193725.00"
    assert finalized.client_project_snapshot["client_name"] == "Client Company"
    project.client_name = "Changed Later"
    project.save(update_fields=["client_name"])
    finalized.refresh_from_db()
    assert finalized.client_project_snapshot["client_name"] == "Client Company"
    with pytest.raises(ValidationError, match="Finalized"):
        update_draft_content(version=finalized, actor=user, data={"scope_summary": "Changed"})
    with pytest.raises(ValidationError, match="Draft Estimate"):
        save_allowance(
            version=estimate,
            actor=user,
            data={"description": "Late", "amount": 1, "currency": "CAD", "treatment": "included"},
        )


def test_finalize_api_without_optional_client_contact_is_atomic_and_succeeds(setup, user, storage):
    project, _, estimate, _, proposal = prepared(setup, user, storage)
    assert proposal.client_contact_id is None
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse(
        "proposal-version-finalize",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "version_pk": proposal.pk,
        },
    )

    response = client.post(url, {}, format="json")

    assert response.status_code == 200
    proposal.refresh_from_db()
    estimate.refresh_from_db()
    assert proposal.status == ProposalVersion.Status.FINALIZED
    assert estimate.status == EstimateVersion.Status.FROZEN
    assert proposal.client_project_snapshot["client_contact"] is None


def test_finalization_guards_and_successor_versioning(setup, user, storage):
    _, estimate, estimate_version, proposal, proposal_version = prepared(setup, user, storage)
    proposal_version.scope_summary = ""
    proposal_version.save(update_fields=["scope_summary"])
    with pytest.raises(ValidationError, match="scope summary"):
        finalize_proposal(version=proposal_version, actor=user)
    proposal_version.scope_summary = "Valid client scope"
    proposal_version.save(update_fields=["scope_summary"])
    finalize_proposal(version=proposal_version, actor=user)
    with pytest.raises(ValidationError, match="Draft proposal"):
        finalize_proposal(version=proposal_version, actor=user)
    successor = create_estimate_version(estimate=estimate, actor=user)
    assert successor.version == estimate_version.version + 1
    assert successor.status == EstimateVersion.Status.DRAFT
    assert proposal.versions.get(version=1).estimate_version_id == estimate_version.pk


def test_pdf_is_ascii_safe_formatted_versioned_and_has_no_internal_leakage(
    setup, user, storage, monkeypatch
):
    project, _, _, _, proposal = prepared(setup, user, storage)
    project.name = "JD Sports — Intercity Shopping Centre"
    project.save(update_fields=["name"])
    finalize_proposal(version=proposal, actor=user)
    fake = FakeObjectStorage()
    monkeypatch.setattr("apps.proposals.pdf.get_object_storage", lambda: fake)
    monkeypatch.setattr("apps.proposals.pdf.TEMPLATE_VERSION", "client-proposal-v1")
    original, created = generate_final_pdf(version=proposal, actor=user)
    monkeypatch.setattr("apps.proposals.pdf.TEMPLATE_VERSION", "client-proposal-v2")
    corrected, corrected_created = generate_final_pdf(version=proposal, actor=user)
    repeated, repeated_created = generate_final_pdf(version=proposal, actor=user)
    assert created is True and corrected_created is True and repeated_created is False
    assert repeated.pk == corrected.pk and original.pk != corrected.pk
    assert original.version == 1 and corrected.version == 2
    assert ProposalPdfArtifact.objects.count() == 2
    stored = fake.objects[corrected.file_asset.storage_key]
    text = "".join(page.get_text() for page in pymupdf.open(stream=stored, filetype="pdf"))
    assert "JD Sports - Intercity Shopping Centre" in text
    assert "Controls allowance - CAD 5,000.00" in text
    assert "Proposed Contract Amount: CAD 193,725.00" in text
    assert " ? " not in text
    assert "ACR" not in text and "leveling" not in text.lower() and "Base Bid" not in text
    assert "176,500.00" not in text and "3,000.00" not in text


def test_permissions_and_download(setup, user, membership, storage, monkeypatch):
    project, _, _, _, proposal = prepared(setup, user, storage)
    finalize_proposal(version=proposal, actor=user)
    fake = FakeObjectStorage()
    monkeypatch.setattr("apps.proposals.pdf.get_object_storage", lambda: fake)
    artifact, _ = generate_final_pdf(version=proposal, actor=user)
    client = APIClient()
    client.force_authenticate(user=user)
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=["role"])
    finalize_url = reverse(
        "proposal-version-finalize",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "version_pk": proposal.pk,
        },
    )
    assert client.post(finalize_url, {}, format="json").status_code == 403
    download_url = reverse(
        "proposal-pdf-download",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "artifact_pk": artifact.pk,
        },
    )
    assert client.get(download_url).status_code == 200
