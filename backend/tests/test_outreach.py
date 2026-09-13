import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError

from apps.analysis.models import ProjectIntelligenceSnapshot
from apps.contractors.models import Company, Contact, ScopeContractorCandidate
from apps.organizations.models import Membership, Organization
from apps.outreach.models import (
    InvitationBatch,
    InvitationCampaign,
    InvitationRecipient,
    InvitationRecipientStatusEvent,
    OutreachMessage,
)
from apps.outreach.services import (
    add_invitation_recipient,
    create_invitation_batch,
    create_invitation_campaign,
    create_outreach_message,
    transition_invitation_recipient_status,
)
from apps.projects.models import AuditEvent, Project
from apps.scope_packages.models import ScopePackage, ScopePackageVersion

pytestmark = pytest.mark.django_db


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
