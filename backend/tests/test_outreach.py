import smtplib
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analysis.models import ProjectIntelligenceSnapshot
from apps.contractors.models import Company, Contact, ScopeContractorCandidate
from apps.contractors.serializers import CandidateSerializer
from apps.contractors.services import build_trade_coverage, set_candidate_status
from apps.organizations.models import Membership, Organization
from apps.outreach.credentials import encrypt_password
from apps.outreach.delivery import (
    approve_batch_send,
    deliver_message,
    prepare_batch_messages,
    readiness,
)
from apps.outreach.models import (
    BatchSendApproval,
    CampaignSetupEvent,
    InvitationBatch,
    InvitationCampaign,
    InvitationRecipient,
    InvitationRecipientStatusEvent,
    OutreachDeliveryAttempt,
    OutreachMessage,
    OutreachSenderSettings,
    OutreachSMTPConfiguration,
)
from apps.outreach.rfq import COMPANY_PLACEHOLDER, RFQ_TEMPLATE_VERSION, build_rfq_preview
from apps.outreach.services import (
    add_invitation_recipient,
    create_invitation_batch,
    create_invitation_campaign,
    create_outreach_message,
    transition_invitation_recipient_status,
)
from apps.outreach.setup import parse_project_local, save_campaign_setup, save_sender_settings
from apps.outreach.smtp import SMTPDeliveryProvider, provider_status
from apps.projects.models import AuditEvent, Project
from apps.scope_packages.models import ScopeItem, ScopePackage, ScopePackageVersion

pytestmark = pytest.mark.django_db
TEST_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")


@pytest.fixture
def setup(user, organization, membership):
    project = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="OUT-1",
        name="Outreach",
        project_timezone="America/Toronto",
    )
    snapshot = ProjectIntelligenceSnapshot.objects.create(
        project=project,
        version=1,
        fingerprint="a" * 64,
        created_by=user,
        manifest={"version": 1},
        summary_counts={"findings": 0},
    )
    package = ScopePackage.objects.create(
        organization=organization,
        project=project,
        source_snapshot=snapshot,
        trade_key="hvac",
        trade_category="HVAC",
        created_by=user,
        updated_by=user,
    )
    ready = ScopePackageVersion.objects.create(
        package=package,
        version=1,
        title="HVAC",
        status=ScopePackageVersion.Status.READY,
        created_by=user,
    )
    package.current_version = ready
    package.save()
    company = Company.objects.create(
        organization=organization,
        display_name="Example Mechanical",
        created_by=user,
        updated_by=user,
    )
    contact = Contact.objects.create(
        company=company,
        name="Pat Example",
        email="pat@example.invalid",
        title="Estimator",
    )
    candidate = ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        scope_version=ready,
        company=company,
        status=ScopeContractorCandidate.Status.APPROVED,
        created_by=user,
        updated_by=user,
    )
    return project, package, ready, candidate, contact


def campaign_for(setup, user):
    project, package, ready, _, _ = setup
    return create_invitation_campaign(
        project=project, scope_package=package, scope_version=ready, actor=user
    )


def test_campaign_exact_ready_version_and_historical_binding(setup, user):
    project, package, ready, _, _ = setup
    campaign = campaign_for(setup, user)
    assert campaign.scope_version_id == ready.id
    draft = ScopePackageVersion.objects.create(
        package=package, version=2, title="Draft", created_by=user
    )
    package.current_version = draft
    package.save()
    campaign.refresh_from_db()
    assert campaign.scope_version_id == ready.id
    with pytest.raises(ValidationError):
        create_invitation_campaign(
            project=project, scope_package=package, scope_version=ready, actor=user
        )
    with pytest.raises(ValidationError):
        create_invitation_campaign(
            project=project, scope_package=package, scope_version=draft, actor=user
        )
    campaign.scope_version = draft
    with pytest.raises(ValidationError):
        campaign.save()


def test_campaign_rejects_wrong_project_and_inactive_package(setup, user):
    project, package, ready, _, _ = setup
    other = Project.objects.create(
        organization=project.organization,
        created_by=user,
        project_number="OUT-2",
        name="Other",
        project_timezone="America/Toronto",
    )
    with pytest.raises(ValidationError):
        create_invitation_campaign(
            project=other, scope_package=package, scope_version=ready, actor=user
        )
    package.lifecycle = ScopePackage.Lifecycle.SUPERSEDED
    package.save()
    with pytest.raises(ValidationError):
        campaign_for(setup, user)


def test_campaign_uses_current_database_scope_not_stale_object(setup, user):
    project, package, ready, _, _ = setup
    stale_package = ScopePackage.objects.get(pk=package.pk)
    draft = ScopePackageVersion.objects.create(
        package=package, version=2, title="Draft", created_by=user
    )
    package.current_version = draft
    package.save()
    with pytest.raises(ValidationError):
        create_invitation_campaign(
            project=project, scope_package=stale_package, scope_version=ready, actor=user
        )


def test_batch_and_recipient_idempotency_and_history(setup, user):
    _, _, _, candidate, contact = setup
    campaign = campaign_for(setup, user)
    first = create_invitation_batch(campaign=campaign, actor=user, sequence=1)
    assert create_invitation_batch(campaign=campaign, actor=user, sequence=1).id == first.id
    second = create_invitation_batch(campaign=campaign, actor=user, sequence=2)
    recipient = add_invitation_recipient(
        batch=first, candidate=candidate, contact=contact, actor=user
    )
    assert (
        add_invitation_recipient(batch=first, candidate=candidate, contact=contact, actor=user).id
        == recipient.id
    )
    assert InvitationRecipientStatusEvent.objects.filter(recipient=recipient).count() == 1
    assert (
        add_invitation_recipient(batch=second, candidate=candidate, contact=contact, actor=user).id
        != recipient.id
    )
    first.campaign = campaign_for(setup, user)
    with pytest.raises(ValidationError):
        first.save()


def test_recipient_requires_explicit_approval_and_valid_contact(setup, user):
    _, _, _, candidate, contact = setup
    batch = create_invitation_batch(campaign=campaign_for(setup, user), actor=user)
    candidate.status = ScopeContractorCandidate.Status.SHORTLISTED
    candidate.save()
    with pytest.raises(ValidationError):
        add_invitation_recipient(batch=batch, candidate=candidate, contact=contact, actor=user)
    candidate.status = ScopeContractorCandidate.Status.APPROVED
    candidate.save()
    contact.is_active = False
    contact.save()
    with pytest.raises(ValidationError):
        add_invitation_recipient(batch=batch, candidate=candidate, contact=contact, actor=user)
    contact.is_active = True
    contact.email = ""
    contact.save()
    with pytest.raises(ValidationError):
        add_invitation_recipient(batch=batch, candidate=candidate, contact=contact, actor=user)


def test_snapshot_status_and_immutable_messages(setup, user):
    _, _, _, candidate, contact = setup
    batch = create_invitation_batch(campaign=campaign_for(setup, user), actor=user)
    recipient = add_invitation_recipient(
        batch=batch, candidate=candidate, contact=contact, actor=user
    )
    v1 = create_outreach_message(
        recipient=recipient,
        actor=user,
        from_name="BB Builders",
        from_address="bids@example.invalid",
        subject="Invitation",
        body="Private content",
    )
    contact.email = "changed@example.invalid"
    contact.save()
    v2 = create_outreach_message(
        recipient=recipient,
        actor=user,
        from_name="BB Builders",
        from_address="bids@example.invalid",
        subject="Revised",
        body="Updated",
    )
    assert (v1.to_address, v2.to_address) == ("pat@example.invalid",) * 2
    assert (v1.sequence, v2.sequence) == (1, 2)
    v1.body = "Changed"
    with pytest.raises(ValidationError):
        v1.save()
    assert not AuditEvent.objects.filter(metadata__icontains="Private content").exists()
    with pytest.raises(ValidationError):
        transition_invitation_recipient_status(
            recipient=recipient, new_status="invited", actor=user
        )
    transition_invitation_recipient_status(
        recipient=recipient, new_status=InvitationRecipient.Status.CANCELLED, actor=user
    )
    assert InvitationRecipientStatusEvent.objects.filter(recipient=recipient).count() == 2
    recipient.refresh_from_db()
    assert recipient.current_status == InvitationRecipient.Status.CANCELLED
    with pytest.raises(ValidationError):
        create_outreach_message(
            recipient=recipient,
            actor=user,
            from_name="BB",
            from_address="bids@example.invalid",
            subject="No",
            body="No",
        )


def test_permissions(setup, user, membership):
    project, package, ready, _, _ = setup
    viewer = get_user_model().objects.create_user(email="viewer@example.invalid", password="test")
    Membership.objects.create(
        user=viewer, organization=project.organization, role=Membership.Role.VIEWER
    )
    with pytest.raises(PermissionDenied):
        create_invitation_campaign(
            project=project, scope_package=package, scope_version=ready, actor=viewer
        )
    membership.is_active = False
    membership.save()
    with pytest.raises(PermissionDenied):
        campaign_for(setup, user)
    membership.is_active = True
    membership.role = Membership.Role.ADMIN
    membership.save()
    assert campaign_for(setup, user).pk
    other_org = Organization.objects.create(name="Other", slug="other")
    outsider = get_user_model().objects.create_user(email="other@example.invalid", password="test")
    Membership.objects.create(user=outsider, organization=other_org, role=Membership.Role.ADMIN)
    with pytest.raises(PermissionDenied):
        create_invitation_campaign(
            project=project, scope_package=package, scope_version=ready, actor=outsider
        )


def test_no_delivery_fields_or_rows_created_implicitly(setup, user):
    campaign_for(setup, user)
    assert InvitationCampaign.objects.count() == 1
    assert InvitationBatch.objects.count() == 0
    assert InvitationRecipient.objects.count() == 0
    assert OutreachMessage.objects.count() == 0


def test_recipient_rejects_mismatched_candidate_version_company_and_contact(setup, user):
    project, package, ready, candidate, contact = setup
    batch = create_invitation_batch(campaign=campaign_for(setup, user), actor=user)
    other_company = Company.objects.create(
        organization=project.organization, display_name="Other", created_by=user, updated_by=user
    )
    other_contact = Contact.objects.create(
        company=other_company, name="Other", email="other@example.invalid"
    )
    with pytest.raises(ValidationError):
        add_invitation_recipient(
            batch=batch, candidate=candidate, contact=other_contact, actor=user
        )
    other_version = ScopePackageVersion.objects.create(
        package=package,
        version=2,
        title="Other Ready",
        status=ScopePackageVersion.Status.READY,
        created_by=user,
    )
    candidate.scope_version = other_version
    candidate.save()
    with pytest.raises(ValidationError):
        add_invitation_recipient(batch=batch, candidate=candidate, contact=contact, actor=user)
    candidate.scope_version = ready
    candidate.company = other_company
    candidate.save()
    with pytest.raises(ValidationError):
        add_invitation_recipient(batch=batch, candidate=candidate, contact=contact, actor=user)


def test_status_and_event_are_append_only(setup, user):
    _, _, _, candidate, contact = setup
    batch = create_invitation_batch(campaign=campaign_for(setup, user), actor=user)
    recipient = add_invitation_recipient(
        batch=batch, candidate=candidate, contact=contact, actor=user
    )
    recipient.current_status = InvitationRecipient.Status.CANCELLED
    with pytest.raises(ValidationError):
        recipient.save()
    event = recipient.status_events.get()
    event.new_status = InvitationRecipient.Status.CANCELLED
    with pytest.raises(ValidationError):
        event.save()
    transition_invitation_recipient_status(
        recipient=recipient, new_status=InvitationRecipient.Status.CANCELLED, actor=user
    )
    transition_invitation_recipient_status(
        recipient=recipient, new_status=InvitationRecipient.Status.CANCELLED, actor=user
    )
    assert recipient.status_events.count() == 2


def test_rfq_preview_uses_exact_campaign_version_and_all_scope_sections(setup, user):
    project, package, ready, _, _ = setup
    ScopePackageVersion.objects.filter(pk=ready.pk).update(
        description="Trade summary",
        inclusions=["Supply ductwork", "Install diffusers"],
        exclusions=["Electrical connection"],
        clarifications=["Confirm roof opening"],
    )
    campaign = campaign_for(setup, user)
    preview = build_rfq_preview(campaign=campaign)
    assert preview.template_version == RFQ_TEMPLATE_VERSION
    assert preview.source_scope_version_id == ready.pk
    assert preview.package_summary == "Trade summary"
    assert preview.inclusions == ("Supply ductwork", "Install diffusers")
    assert preview.exclusions == ("Electrical connection",)
    assert preview.clarifications == ("Confirm roof opening",)
    assert all(
        text in preview.body
        for text in (
            "Supply ductwork",
            "Electrical connection",
            "Confirm roof opening",
            "base bid",
            "taxes",
            "allowances",
            "alternates",
            "permit responsibility",
            "schedule",
            "bid validity",
        )
    )
    assert COMPANY_PLACEHOLDER in preview.body
    assert preview.bid_deadline is None and preview.questions_deadline is None
    assert "Not provided; confirm with BB Builders" in preview.body
    newer = ScopePackageVersion.objects.create(
        package=package,
        version=2,
        title="New Draft",
        inclusions=["Different work"],
        created_by=user,
    )
    package.current_version = newer
    package.save()
    historical = build_rfq_preview(campaign=campaign)
    assert historical == preview
    assert "Different work" not in historical.body
    assert OutreachMessage.objects.count() == 0


def test_rfq_deadlines_are_real_and_validated(setup, user):
    project, _, _, _, _ = setup
    campaign = campaign_for(setup, user)
    bid = timezone.now() + timedelta(days=10)
    campaign.bid_deadline = bid
    campaign.questions_deadline = bid - timedelta(days=2)
    campaign.save()
    preview = build_rfq_preview(campaign=campaign)
    assert preview.bid_deadline is not None
    assert preview.questions_deadline is not None
    assert preview.bid_deadline in preview.body
    assert preview.questions_deadline in preview.body
    campaign.questions_deadline = bid + timedelta(days=1)
    with pytest.raises(ValidationError):
        campaign.save()


def test_rfq_classifies_frozen_items_without_promoting_uncertain_or_coordination(setup, user):
    _, package, ready, _, _ = setup
    examples = [
        ("confirmed", "Install supply ductwork", "supply_install", "supply_install", False),
        ("balance", "HVAC system shall be tested and balanced", "testing", "unclear", False),
        ("clean", "Ventilation contractor shall clean existing ducts", "general", "unclear", False),
        ("controls", "CONTROL WIRING SHALL BE BY HVAC CONTRACTOR", "controls", "unclear", True),
        ("thermostat", "Dismantle existing thermostat", "demolition", "unclear", False),
        ("glass", "Provide glass to ASTM E1300", "supply_install", "unclear", False),
        ("electrical", "Coordinate cable tray and conduit", "coordination", "unclear", True),
        ("plumbing", "Provide water hammer arrestors", "equipment", "unclear", False),
        ("lighting", "Install track lighting", "supply_install", "unclear", False),
        (
            "coordination",
            "Coordinate diffuser and lighting fixture locations",
            "coordination",
            "unclear",
            True,
        ),
        ("question", "Confirm existing duct location", "supply_install", "unclear", False),
        ("other", "Equipment by others", "equipment", "by_others", False),
        (
            "admin",
            "Shop drawings shall be submitted by this contractor",
            "submittals",
            "unclear",
            False,
        ),
    ]
    for sequence, (key, text, item_type, responsibility, coordination_required) in enumerate(
        examples, start=1
    ):
        ScopeItem.objects.create(
            package_version=ready,
            item_key=key,
            item_type=item_type,
            responsibility=responsibility,
            coordination_required=coordination_required,
            title=text,
            description=text,
            sequence=sequence,
        )
    ScopePackageVersion.objects.filter(pk=ready.pk).update(
        inclusions=[example[1] for example in examples],
        exclusions=["Electrical connection excluded"],
        clarifications=["Confirm roof access"],
    )
    campaign = campaign_for(setup, user)
    preview = build_rfq_preview(campaign=campaign)
    assert preview.inclusions == (
        "Install supply ductwork",
        "HVAC system shall be tested and balanced",
        "Ventilation contractor shall clean existing ducts",
        "CONTROL WIRING SHALL BE BY HVAC CONTRACTOR",
        "Dismantle existing thermostat",
    )
    assert preview.exclusions == ("Electrical connection excluded",)
    assert preview.clarifications == (
        "Confirm roof access",
        "Confirm existing duct location",
    )
    assert preview.coordination_requirements == (
        "Coordinate diffuser and lighting fixture locations",
    )
    assert preview.general_requirements == ("Shop drawings shall be submitted by this contractor",)
    assert preview.omitted_unrelated_count == 5
    inclusion_section = preview.body.split("Scope inclusions:", 1)[1].split("Scope exclusions:", 1)[
        0
    ]
    assert "glass" not in inclusion_section and "cable tray" not in inclusion_section
    assert "Coordination requirements (not confirmed trade scope):" in preview.body
    assert "General / project requirements:" in preview.body
    assert "Canada" in preview.body
    assert ScopePackageVersion.objects.get(pk=ready.pk).inclusions == [
        example[1] for example in examples
    ]


def test_rfq_api_is_read_only_and_organization_scoped(setup, user):
    project, _, _, _, _ = setup
    campaign = campaign_for(setup, user)
    path = reverse(
        "outreach-campaign-rfq-preview",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "campaign_pk": campaign.pk,
        },
    )
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(path)
    assert response.status_code == 200
    assert response.data["source_scope_version_id"] == campaign.scope_version_id
    assert client.post(path, {}).status_code == 405
    assert client.patch(path, {}).status_code == 405
    viewer = get_user_model().objects.create_user(
        email="rfq-viewer@example.invalid", password="test"
    )
    Membership.objects.create(
        user=viewer, organization=project.organization, role=Membership.Role.VIEWER
    )
    client.force_authenticate(viewer)
    assert client.get(path).status_code == 200
    assert client.post(path, {}).status_code == 405
    outsider = get_user_model().objects.create_user(
        email="rfq-outsider@example.invalid", password="test"
    )
    client.force_authenticate(outsider)
    assert client.get(path).status_code == 403
    client.force_authenticate(user)
    wrong_project = Project.objects.create(
        organization=project.organization,
        created_by=user,
        project_number="OUT-OTHER",
        name="Other",
        project_timezone="America/Toronto",
    )
    wrong_path = reverse(
        "outreach-campaign-rfq-preview",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": wrong_project.pk,
            "campaign_pk": campaign.pk,
        },
    )
    assert client.get(wrong_path).status_code == 404
    assert InvitationBatch.objects.count() == 0
    assert InvitationRecipient.objects.count() == 0
    assert OutreachMessage.objects.count() == 0


def test_explicit_approval_requires_shortlist_current_ready_and_email(setup, user):
    project, package, ready, candidate, contact = setup
    candidate.status = ScopeContractorCandidate.Status.SHORTLISTED
    candidate.save(update_fields=("status",))
    assert CandidateSerializer(candidate).data["outreach_eligibility"]["can_approve"] is False
    with pytest.raises(ValidationError):
        set_candidate_status(
            candidate=candidate, status=ScopeContractorCandidate.Status.APPROVED, actor=user
        )
    contact.is_primary = True
    contact.save(update_fields=("is_primary",))
    assert CandidateSerializer(candidate).data["outreach_eligibility"] == {
        "can_approve": True,
        "can_revoke": False,
        "reason": "",
    }
    approved, changed = set_candidate_status(
        candidate=candidate, status=ScopeContractorCandidate.Status.APPROVED, actor=user
    )
    assert changed and approved.status == ScopeContractorCandidate.Status.APPROVED
    assert CandidateSerializer(approved).data["outreach_eligibility"]["can_revoke"] is True
    assert build_trade_coverage(project=project)["trades"][0]["shortlisted_count"] == 1
    assert (
        AuditEvent.objects.filter(action_code="contractor_candidate.approved_for_outreach").count()
        == 1
    )
    again, changed = set_candidate_status(
        candidate=candidate, status=ScopeContractorCandidate.Status.APPROVED, actor=user
    )
    assert not changed and again.pk == candidate.pk
    reverted, changed = set_candidate_status(
        candidate=candidate, status=ScopeContractorCandidate.Status.SHORTLISTED, actor=user
    )
    assert changed and reverted.status == ScopeContractorCandidate.Status.SHORTLISTED
    candidate.scope_version = ScopePackageVersion.objects.create(
        package=package, version=2, title="Draft", created_by=user
    )
    candidate.save(update_fields=("scope_version",))
    with pytest.raises(ValidationError):
        set_candidate_status(
            candidate=candidate, status=ScopeContractorCandidate.Status.APPROVED, actor=user
        )


def test_outreach_workspace_explicit_campaign_batch_recipient_and_preview(setup, user):
    project, package, ready, candidate, contact = setup
    slug = project.organization.slug
    client = APIClient()
    client.force_authenticate(user)
    workspace_url = reverse(
        "outreach-workspace", kwargs={"organization_slug": slug, "project_pk": project.pk}
    )
    campaign_url = reverse(
        "outreach-campaign-create", kwargs={"organization_slug": slug, "project_pk": project.pk}
    )
    workspace = client.get(workspace_url)
    assert workspace.status_code == 200
    assert len(workspace.data["trades"]) == 1
    assert workspace.data["trades"][0]["approved_count"] == 1
    assert workspace.data["trades"][0]["campaign"] is None
    assert InvitationCampaign.objects.count() == 0
    response = client.post(
        campaign_url, {"scope_package_id": package.pk, "scope_version_id": ready.pk}
    )
    assert response.status_code == 200, response.data
    campaign_id = response.data["id"]
    assert (
        client.post(
            campaign_url, {"scope_package_id": package.pk, "scope_version_id": ready.pk}
        ).data["id"]
        == campaign_id
    )
    batch_url = reverse(
        "outreach-batch-create",
        kwargs={"organization_slug": slug, "project_pk": project.pk, "campaign_pk": campaign_id},
    )
    response = client.post(batch_url, {"sequence": 1})
    assert response.status_code == 200, response.data
    batch_id = response.data["id"]
    assert client.post(batch_url, {"sequence": 1}).data["id"] == batch_id
    recipient_url = reverse(
        "outreach-recipient-create",
        kwargs={"organization_slug": slug, "project_pk": project.pk, "batch_pk": batch_id},
    )
    response = client.post(recipient_url, {"candidate_id": candidate.pk, "contact_id": contact.pk})
    assert response.status_code == 200, response.data
    assert (
        client.post(recipient_url, {"candidate_id": candidate.pk, "contact_id": contact.pk}).data[
            "id"
        ]
        == response.data["id"]
    )
    assert InvitationRecipient.objects.count() == 1
    assert InvitationRecipient.objects.get().email == contact.email
    assert OutreachMessage.objects.count() == 0
    preview_url = reverse(
        "outreach-campaign-rfq-preview",
        kwargs={"organization_slug": slug, "project_pk": project.pk, "campaign_pk": campaign_id},
    )
    assert client.get(preview_url).data["source_scope_version_id"] == ready.pk
    with pytest.raises(ValidationError):
        set_candidate_status(
            candidate=candidate, status=ScopeContractorCandidate.Status.SHORTLISTED, actor=user
        )
    assert CandidateSerializer(candidate).data["outreach_eligibility"]["can_revoke"] is False


def test_outreach_viewer_and_cross_project_safety(setup, user):
    project, package, ready, candidate, contact = setup
    slug = project.organization.slug
    viewer = get_user_model().objects.create_user(
        email="m303-viewer@example.invalid", password="test"
    )
    Membership.objects.create(
        user=viewer, organization=project.organization, role=Membership.Role.VIEWER
    )
    client = APIClient()
    client.force_authenticate(viewer)
    workspace_url = reverse(
        "outreach-workspace", kwargs={"organization_slug": slug, "project_pk": project.pk}
    )
    campaign_url = reverse(
        "outreach-campaign-create", kwargs={"organization_slug": slug, "project_pk": project.pk}
    )
    assert client.get(workspace_url).status_code == 200
    assert (
        client.post(
            campaign_url, {"scope_package_id": package.pk, "scope_version_id": ready.pk}
        ).status_code
        == 403
    )
    client.force_authenticate(user)
    other = Project.objects.create(
        organization=project.organization,
        created_by=user,
        project_number="OUT-X",
        name="Other",
        project_timezone="America/Toronto",
    )
    wrong_url = reverse(
        "outreach-campaign-create", kwargs={"organization_slug": slug, "project_pk": other.pk}
    )
    assert (
        client.post(
            wrong_url, {"scope_package_id": package.pk, "scope_version_id": ready.pk}
        ).status_code
        == 404
    )
    assert InvitationCampaign.objects.count() == 0


def delivery_batch(setup, user):
    project, _, _, candidate, contact = setup
    campaign = campaign_for(setup, user)
    batch = create_invitation_batch(campaign=campaign, actor=user)
    add_invitation_recipient(batch=batch, candidate=candidate, contact=contact, actor=user)
    return project, batch


@pytest.fixture
def smtp_configured():
    with override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY):
        yield


@pytest.fixture
def smtp_ready(monkeypatch, smtp_configured):
    monkeypatch.setattr(
        "apps.outreach.delivery.SMTPDeliveryProvider.deliver",
        lambda self, *, message, idempotency_key: "",
    )
    yield


def configure_delivery(project, batch, user):
    campaign = batch.campaign
    campaign.bid_deadline = timezone.now() + timedelta(days=10)
    campaign.setup_version += 1
    campaign.save()
    OutreachSenderSettings.objects.create(
        organization=project.organization,
        display_name="BB Builders",
        from_address="bids@example.invalid",
        reply_to="reply@example.invalid",
        updated_by=user,
    )
    OutreachSMTPConfiguration.objects.create(
        organization=project.organization,
        host="smtp.example.invalid",
        port=587,
        username="test-user",
        encrypted_password=encrypt_password("test-password"),
        security=OutreachSMTPConfiguration.Security.STARTTLS,
        timeout_seconds=20,
        is_enabled=True,
        updated_by=user,
    )
    return campaign


def test_delivery_readiness_approval_and_idempotent_smtp_send(setup, user, smtp_ready):
    project, batch = delivery_batch(setup, user)
    assert "bid_deadline_required" in {item["code"] for item in readiness(batch)["blockers"]}
    with pytest.raises(ValidationError):
        approve_batch_send(batch=batch, actor=user)
    configure_delivery(project, batch, user)
    messages = prepare_batch_messages(batch=batch, actor=user)
    assert [item.pk for item in prepare_batch_messages(batch=batch, actor=user)] == [messages[0].pk]
    assert OutreachMessage.objects.count() == 1
    assert messages[0].to_address == batch.recipients.get().email
    assert "Example Mechanical" in messages[0].body
    assert "send_approval_required" in {item["code"] for item in readiness(batch)["blockers"]}
    approval = approve_batch_send(batch=batch, actor=user)
    assert approve_batch_send(batch=batch, actor=user).pk == approval.pk
    assert BatchSendApproval.objects.count() == 1
    attempt = deliver_message(message=messages[0], actor=user)
    assert attempt.status == OutreachDeliveryAttempt.Status.SUCCEEDED
    with pytest.raises(ValidationError):
        deliver_message(message=messages[0], actor=user)
    assert OutreachDeliveryAttempt.objects.count() == 1
    assert batch.recipients.get().current_status == InvitationRecipient.Status.INVITED
    assert batch.recipients.get().status_events.filter(new_status="invited").count() == 1
    assert AuditEvent.objects.filter(action_code="outreach_delivery.succeeded").count() == 1
    assert all(
        "Example Mechanical" not in str(event.metadata)
        and "pat@example.invalid" not in str(event.metadata)
        for event in AuditEvent.objects.filter(action_code__startswith="outreach_delivery.")
    )


def test_delivery_failure_preserved_explicit_retry_and_permissions(
    setup, user, monkeypatch, smtp_ready
):
    project, batch = delivery_batch(setup, user)
    configure_delivery(project, batch, user)
    message = prepare_batch_messages(batch=batch, actor=user)[0]
    approve_batch_send(batch=batch, actor=user)

    def fail(self, *, message, idempotency_key):
        raise RuntimeError("Secret provider failure")

    with monkeypatch.context() as patcher:
        patcher.setattr("apps.outreach.delivery.SMTPDeliveryProvider.deliver", fail)
        first = deliver_message(message=message, actor=user)
    assert first.status == OutreachDeliveryAttempt.Status.FAILED
    assert "Secret" not in first.safe_error_message
    assert batch.recipients.get().current_status == InvitationRecipient.Status.PREPARED
    with pytest.raises(ValidationError):
        deliver_message(message=message, actor=user)
    second = deliver_message(message=message, actor=user, retry=True)
    assert second.status == OutreachDeliveryAttempt.Status.SUCCEEDED
    assert second.sequence == 2
    first.refresh_from_db()
    assert first.status == OutreachDeliveryAttempt.Status.FAILED
    viewer = get_user_model().objects.create_user(
        email="delivery-viewer@example.invalid", password="test"
    )
    Membership.objects.create(
        user=viewer, organization=project.organization, role=Membership.Role.VIEWER
    )
    with pytest.raises(PermissionDenied):
        deliver_message(message=message, actor=viewer)


def test_delivery_api_blocks_missing_bid_due_and_viewer_writes(setup, user):
    project, batch = delivery_batch(setup, user)
    url = reverse(
        "outreach-batch-delivery",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "batch_pk": batch.pk,
            "action": "approve",
        },
    )
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(url)
    assert response.status_code == 200
    assert "bid_deadline_required" in {item["code"] for item in response.data["blockers"]}
    assert client.post(url, {}).status_code == 400
    assert BatchSendApproval.objects.count() == 0
    assert OutreachMessage.objects.count() == 0
    assert OutreachDeliveryAttempt.objects.count() == 0
    viewer = get_user_model().objects.create_user(
        email="delivery-api-viewer@example.invalid", password="test"
    )
    Membership.objects.create(
        user=viewer, organization=project.organization, role=Membership.Role.VIEWER
    )
    client.force_authenticate(viewer)
    assert client.get(url).status_code == 200
    assert client.post(url, {}).status_code == 403
    other = Project.objects.create(
        organization=project.organization,
        created_by=user,
        project_number="OUT-OTHER-DELIVERY",
        name="Other",
        project_timezone="America/Toronto",
    )
    wrong = reverse(
        "outreach-batch-delivery",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": other.pk,
            "batch_pk": batch.pk,
            "action": "approve",
        },
    )
    client.force_authenticate(user)
    assert client.get(wrong).status_code == 404


def test_delivery_missing_sender_blocks_send_approval(setup, user, smtp_ready):
    project, batch = delivery_batch(setup, user)
    campaign = batch.campaign
    campaign.bid_deadline = timezone.now() + timedelta(days=10)
    campaign.save()
    assert "sender_required" in {item["code"] for item in readiness(batch)["blockers"]}
    with pytest.raises(ValidationError):
        approve_batch_send(batch=batch, actor=user)


def test_changed_message_requires_new_send_approval(setup, user, smtp_ready):
    project, batch = delivery_batch(setup, user)
    campaign = configure_delivery(project, batch, user)
    first = prepare_batch_messages(batch=batch, actor=user)[0]
    approval = approve_batch_send(batch=batch, actor=user)
    assert readiness(InvitationBatch.objects.get(pk=batch.pk))["ready"]
    campaign.bid_deadline += timedelta(days=1)
    campaign.setup_version += 1
    campaign.save()
    second = prepare_batch_messages(batch=batch, actor=user)[0]
    assert second.pk != first.pk
    assert first.body != second.body
    state = readiness(InvitationBatch.objects.get(pk=batch.pk))
    assert not state["send_approved"]
    assert "send_approval_stale" in {item["code"] for item in state["blockers"]}
    with pytest.raises(ValidationError):
        deliver_message(message=second, actor=user)
    renewed = approve_batch_send(batch=batch, actor=user)
    assert renewed.pk != approval.pk
    assert BatchSendApproval.objects.count() == 2
    assert first.body == OutreachMessage.objects.get(pk=first.pk).body


def test_batch_approval_remains_valid_during_multi_recipient_delivery(setup, user, smtp_ready):
    project, batch = delivery_batch(setup, user)
    _, package, ready, _, _ = setup
    second_company = Company.objects.create(
        organization=project.organization,
        display_name="Second Mechanical",
        created_by=user,
        updated_by=user,
    )
    second_contact = Contact.objects.create(
        company=second_company, name="Second Estimator", email="second@example.invalid"
    )
    second_candidate = ScopeContractorCandidate.objects.create(
        project=project,
        scope_package=package,
        scope_version=ready,
        company=second_company,
        status=ScopeContractorCandidate.Status.APPROVED,
        created_by=user,
        updated_by=user,
    )
    add_invitation_recipient(
        batch=batch, candidate=second_candidate, contact=second_contact, actor=user
    )
    configure_delivery(project, batch, user)
    messages = prepare_batch_messages(batch=batch, actor=user)
    approve_batch_send(batch=batch, actor=user)
    assert readiness(InvitationBatch.objects.get(pk=batch.pk))["send_approved"]
    assert deliver_message(message=messages[0], actor=user).status == "succeeded"
    assert readiness(InvitationBatch.objects.get(pk=batch.pk))["send_approved"]
    assert deliver_message(message=messages[1], actor=user).status == "succeeded"
    assert OutreachDeliveryAttempt.objects.count() == 2


def test_campaign_setup_is_local_audited_and_stales_prepared_message(setup, user, smtp_ready):
    project, batch = delivery_batch(setup, user)
    configure_delivery(project, batch, user)
    first = prepare_batch_messages(batch=batch, actor=user)[0]
    approve_batch_send(batch=batch, actor=user)
    local_bid = (
        (timezone.now() + timedelta(days=15))
        .astimezone(__import__("zoneinfo").ZoneInfo(project.project_timezone))
        .strftime("%Y-%m-%dT%H:%M")
    )
    campaign = save_campaign_setup(
        campaign=batch.campaign, actor=user, bid_local=local_bid, questions_local=""
    )
    assert campaign.setup_version == 2
    assert CampaignSetupEvent.objects.filter(campaign=campaign).count() == 1
    assert "messages_stale" in {item["code"] for item in readiness(batch)["blockers"]}
    second = prepare_batch_messages(batch=batch, actor=user)[0]
    assert second.pk != first.pk
    assert second.source_scope_version_id == campaign.scope_version_id
    assert second.bid_deadline == campaign.bid_deadline
    assert not readiness(batch)["send_approved"]
    assert OutreachMessage.objects.get(pk=first.pk).body == first.body


def test_sender_admin_only_and_provider_status_has_no_secret(
    setup, user, membership, smtp_configured
):
    project = setup[0]
    with pytest.raises(PermissionDenied):
        save_sender_settings(
            organization=project.organization,
            actor=user,
            display_name="BB Builders",
            from_address="bids@example.invalid",
            reply_to="reply@example.invalid",
        )
    membership.role = Membership.Role.ADMIN
    membership.save()
    sender = save_sender_settings(
        organization=project.organization,
        actor=user,
        display_name="BB Builders",
        from_address="bids@example.invalid",
        reply_to="reply@example.invalid",
    )
    assert sender.is_enabled
    OutreachSMTPConfiguration.objects.create(
        organization=project.organization,
        host="smtp.example.invalid",
        port=587,
        username="private-user",
        encrypted_password=encrypt_password("private-password"),
        security="starttls",
        timeout_seconds=20,
        is_enabled=True,
        updated_by=user,
    )
    state = provider_status(project.organization)
    assert state["state"] == "configured"
    assert "private" not in str(state)


def test_smtp_adapter_uses_frozen_message_and_mocked_transport(
    setup, user, monkeypatch, smtp_configured
):
    project, batch = delivery_batch(setup, user)
    configure_delivery(project, batch, user)
    message = prepare_batch_messages(batch=batch, actor=user)[0]
    sent = []

    class StubSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self, **kwargs):
            return None

        def login(self, username, password):
            assert username == "test-user"
            assert password == "test-password"

        def send_message(self, email):
            sent.append(email)
            return {}

    monkeypatch.setattr(smtplib, "SMTP", StubSMTP)
    SMTPDeliveryProvider().deliver(message=message, idempotency_key="safe-test-key")
    assert len(sent) == 1
    assert sent[0]["To"] == message.to_address
    assert sent[0]["Subject"] == message.subject
    assert message.body in sent[0].get_content()


def test_setup_and_sender_api_permissions_and_scoping(setup, user, membership):
    project, batch = delivery_batch(setup, user)
    campaign = batch.campaign
    setup_url = reverse(
        "outreach-campaign-setup",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "campaign_pk": campaign.pk,
        },
    )
    sender_url = reverse(
        "outreach-sender-settings",
        kwargs={
            "organization_slug": project.organization.slug,
        },
    )
    client = APIClient()
    client.force_authenticate(user)
    assert client.get(setup_url).status_code == 200
    assert client.get(sender_url).status_code == 200
    assert (
        client.put(
            sender_url,
            {
                "display_name": "BB Builders",
                "from_address": "bids@example.invalid",
                "reply_to": "reply@example.invalid",
                "is_enabled": True,
            },
        ).status_code
        == 403
    )
    viewer = get_user_model().objects.create_user(
        email="sender-viewer@example.invalid", password="test"
    )
    Membership.objects.create(
        user=viewer, organization=project.organization, role=Membership.Role.VIEWER
    )
    client.force_authenticate(viewer)
    assert client.get(setup_url).status_code == 200
    assert (
        client.put(setup_url, {"bid_due_local": "", "questions_due_local": ""}).status_code == 403
    )
    assert client.get(sender_url).status_code == 200
    assert client.put(sender_url, {}).status_code == 403
    membership.role = Membership.Role.ADMIN
    membership.save()
    client.force_authenticate(user)
    assert (
        client.put(
            sender_url,
            {
                "display_name": "BB Builders",
                "from_address": "bids@example.invalid",
                "reply_to": "reply@example.invalid",
                "is_enabled": True,
            },
        ).status_code
        == 200
    )
    other = Project.objects.create(
        organization=project.organization,
        created_by=user,
        project_number="OUT-OTHER-SETUP",
        name="Other",
        project_timezone="America/Toronto",
    )
    wrong_url = reverse(
        "outreach-campaign-setup",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": other.pk,
            "campaign_pk": campaign.pk,
        },
    )
    assert client.get(wrong_url).status_code == 404


def test_campaign_local_time_validation_and_optional_questions(setup, user):
    project, batch = delivery_batch(setup, user)
    assert parse_project_local("2026-09-20T12:30", project.project_timezone).hour == 12
    with pytest.raises(ValidationError):
        parse_project_local("2026-09-20", project.project_timezone)
    with pytest.raises(ValidationError):
        parse_project_local("2026-11-01T01:30", project.project_timezone)
    with pytest.raises(ValidationError):
        parse_project_local("2027-03-14T02:30", project.project_timezone)
    future = (
        (timezone.now() + timedelta(days=20))
        .astimezone(ZoneInfo(project.project_timezone))
        .strftime("%Y-%m-%dT%H:%M")
    )
    campaign = save_campaign_setup(
        campaign=batch.campaign, actor=user, bid_local=future, questions_local=""
    )
    assert campaign.questions_deadline is None
    assert campaign.bid_deadline.tzinfo is not None
    with pytest.raises(ValidationError):
        save_campaign_setup(
            campaign=campaign,
            actor=user,
            bid_local="2020-01-01T12:00",
            questions_local="",
        )
    with pytest.raises(ValidationError):
        save_campaign_setup(
            campaign=campaign,
            actor=user,
            bid_local=future,
            questions_local=future,
        )


def test_provider_readiness_never_opens_smtp_connection(setup, user, monkeypatch, smtp_configured):
    project, batch = delivery_batch(setup, user)
    configure_delivery(project, batch, user)
    monkeypatch.setattr(
        smtplib, "SMTP", lambda *args, **kwargs: pytest.fail("SMTP connected on GET")
    )
    config = OutreachSMTPConfiguration.objects.get(organization=project.organization)
    assert provider_status(project.organization)["state"] == "configured"
    readiness(batch)
    config.is_enabled = False
    config.save()
    assert provider_status(project.organization)["state"] == "disabled"
    assert "delivery_not_configured" in {item["code"] for item in readiness(batch)["blockers"]}
    config.is_enabled = True
    config.host = ""
    config.save()
    assert provider_status(project.organization)["state"] == "misconfigured"
