"""M3-07 commercial interpretation is separate from immutable original quotes."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analysis.providers import ProviderFailure, ProviderResult
from apps.outreach.bid_extraction import (
    process_bid_extraction,
    request_extraction,
    validate_candidates,
)
from apps.outreach.bid_intake import record_manual_quote
from apps.outreach.bid_revisions import (
    create_revision,
    decide_candidate,
    decimal_money,
    mark_ready,
    readiness,
    save_commercial_item,
    save_scope_coverage,
    save_summary,
)
from apps.outreach.models import BidCandidateDecision, BidExtractionRun, BidRevision, BidSubmission
from apps.outreach.views import bid_submission_data
from apps.scope_packages.models import ScopeItem

from .test_bid_intake import setup as intake_setup
from .test_bid_intake import storage as intake_storage
from .test_outreach_responses import fixture_outreach

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n% synthetic test quote\n%%EOF\n"


@pytest.fixture
def setup(user, organization, membership):
    return intake_setup.__wrapped__(user, organization, membership)


@pytest.fixture
def storage(monkeypatch):
    return intake_storage.__wrapped__(monkeypatch)


def source(setup, user):
    project, recipient, _ = fixture_outreach(setup, user)
    submission = record_manual_quote(
        recipient=recipient,
        actor=user,
        files=[SimpleUploadedFile("quote.pdf", PDF, content_type="application/pdf")],
        received_at=timezone.now(),
    )
    return project, submission


def test_inbox_structured_status_is_separate_from_received_intake_status(setup, user, storage):
    project, first = source(setup, user)
    second = record_manual_quote(
        recipient=first.recipient,
        actor=user,
        files=[SimpleUploadedFile("manual.pdf", PDF, content_type="application/pdf")],
        received_at=timezone.now(),
    )
    assert bid_submission_data(first)["structured_status"] == "not_started"
    draft = create_revision(submission=first, actor=user)
    assert bid_submission_data(first)["structured_status"] == "draft"
    BidRevision.objects.filter(pk=draft.pk).update(status="ready")
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse(
        "bid-submission-list",
        kwargs={"organization_slug": first.organization.slug, "project_pk": project.pk},
    )
    response = client.get(url)
    assert response.status_code == 200
    statuses = {item["id"]: item for item in response.data["submissions"]}
    assert statuses[first.pk]["structured_status"] == "ready"
    assert statuses[second.pk]["structured_status"] == "not_started"
    assert statuses[first.pk]["status"] == first.status
    assert statuses[second.pk]["status"] == second.status


def test_decimal_money_is_exact_and_rejects_ambiguous_or_nonfinite():
    assert decimal_money("6500") == Decimal("6500.00")
    assert decimal_money("0") == Decimal("0.00")
    assert decimal_money(None) is None
    for value in ("6,500", "$6500", "NaN", "Infinity", "-4", "1.234", 6500.0):
        with pytest.raises(ValidationError):
            decimal_money(value)


def test_revision_requires_explicit_creation_and_later_submission_does_not_supersede(
    setup, user, storage
):
    _, first = source(setup, user)
    second = record_manual_quote(
        recipient=first.recipient,
        actor=user,
        files=[SimpleUploadedFile("later.pdf", PDF, content_type="application/pdf")],
        received_at=timezone.now(),
    )
    assert BidRevision.objects.count() == 0
    original = create_revision(
        submission=first,
        actor=user,
        label="Original",
        request_key="dcbb48e1-9722-4e5b-b254-2343508975d5",
    )
    replay = create_revision(
        submission=first,
        actor=user,
        label="Original",
        request_key="dcbb48e1-9722-4e5b-b254-2343508975d5",
    )
    assert replay.pk == original.pk
    newer = create_revision(submission=second, actor=user, label="Rev A")
    assert (original.sequence, newer.sequence) == (1, 2)
    assert newer.supersedes_id is None
    assert original.submission_id == first.pk
    assert original.scope_version_id == newer.scope_version_id
    assert BidSubmission.objects.count() == 2
    explicit = create_revision(submission=second, actor=user, supersedes=original)
    assert explicit.supersedes_id == original.pk
    assert original.pk != newer.pk


def test_commercial_items_are_separate_and_unknown_is_not_zero(setup, user, storage):
    _, submission = source(setup, user)
    revision = create_revision(submission=submission, actor=user)
    assert revision.base_bid is None
    assert revision.base_bid_review == "unreviewed"
    save_summary(
        revision=revision,
        actor=user,
        values={
            "base_bid": None,
            "base_bid_review": "not_stated",
            "currency_review": "not_stated",
            "tax_reviewed": True,
        },
    )
    revision.refresh_from_db()
    assert revision.base_bid is None and revision.base_bid_review == "not_stated"
    assert revision.tax_treatment == "not_stated"
    add = save_commercial_item(
        revision=revision,
        actor=user,
        values={
            "kind": "alternate",
            "title": "Upgrade controls",
            "treatment": "add",
            "amount": "6500",
            "currency": "CAD",
        },
    )
    deduct = save_commercial_item(
        revision=revision,
        actor=user,
        values={
            "kind": "alternate",
            "title": "Delete painting",
            "treatment": "deduct",
            "amount": "2000.00",
            "currency": "CAD",
        },
    )
    allowance = save_commercial_item(
        revision=revision,
        actor=user,
        values={
            "kind": "allowance",
            "title": "Temporary heat",
            "amount": "5000",
            "currency": "CAD",
            "included_in_base": "unclear",
        },
    )
    fee = save_commercial_item(
        revision=revision,
        actor=user,
        values={
            "kind": "fee",
            "title": "Permit",
            "category": "permits",
            "treatment": "not_stated",
        },
    )
    exclusion = save_commercial_item(
        revision=revision,
        actor=user,
        values={
            "kind": "exclusion",
            "title": "Roof patching",
            "description": "Explicitly excluded",
        },
    )
    condition = save_commercial_item(
        revision=revision, actor=user, values={"kind": "condition", "title": "Normal working hours"}
    )
    assert add.amount == Decimal("6500.00") and deduct.amount == Decimal("2000.00")
    assert allowance.included_in_base == "unclear"
    assert {item.kind for item in (fee, exclusion, condition)} == {"fee", "exclusion", "condition"}
    assert revision.base_bid is None  # Alternates and allowances never fold into base.


def test_scope_difference_uses_exact_version_and_not_addressed_is_not_excluded(
    setup, user, storage
):
    _, submission = source(setup, user)
    revision = create_revision(submission=submission, actor=user)
    scope_item = ScopeItem.objects.create(
        package_version=submission.scope_version,
        item_key="test-duct",
        item_type="general",
        responsibility="unclear",
        title="Ductwork",
        description="Test",
        sequence=1,
    )
    coverage = save_scope_coverage(
        revision=revision,
        actor=user,
        scope_item=scope_item,
        state="not_addressed",
        reviewed=True,
    )
    assert coverage.state == "not_addressed"
    with pytest.raises(ValidationError):
        save_scope_coverage(
            revision=revision,
            actor=user,
            scope_item=scope_item,
            state="excluded",
            reviewed=True,
        )
    assert coverage.scope_item.package_version_id == revision.scope_version_id


def test_ready_freezes_revision_items_and_human_gate(setup, user, storage):
    _, submission = source(setup, user)
    revision = create_revision(submission=submission, actor=user)
    assert set(readiness(revision)) >= {
        "currency_not_reviewed",
        "base_bid_not_reviewed",
        "tax_not_reviewed",
    }
    with pytest.raises(ValidationError):
        mark_ready(revision=revision, actor=user)
    save_summary(
        revision=revision,
        actor=user,
        values={
            "currency": "CAD",
            "currency_review": "confirmed",
            "base_bid": "185000.00",
            "base_bid_review": "confirmed",
            "tax_treatment": "extra",
            "tax_reviewed": True,
            "commercial_items_reviewed": True,
            "scope_reviewed": True,
        },
    )
    ready = mark_ready(revision=revision, actor=user)
    assert ready.status == "ready" and ready.reviewed_by_id == user.pk
    assert mark_ready(revision=ready, actor=user).pk == ready.pk
    ready.estimator_notes = "Silently edited"
    with pytest.raises(ValidationError):
        ready.save()
    with pytest.raises(ValidationError):
        save_commercial_item(
            revision=ready,
            actor=user,
            values={
                "kind": "condition",
                "title": "Late condition",
            },
        )
    assert ready.submission.attachments.count() == 1


def test_ai_candidate_requires_exact_page_and_safe_amount():
    page = [{"page_number": 1, "text": "Base Bid $6,500. Alternate add $500."}]
    candidate = {
        "kind": "base_bid",
        "title": "Base Bid",
        "description": "Quoted",
        "amount": "6500",
        "currency": "CAD",
        "treatment": None,
        "scope_item_id": None,
        "included_in_base_bid": None,
        "page_number": 1,
        "excerpt": "Base Bid $6,500",
    }
    result = validate_candidates({"candidates": [candidate]}, page, set())
    assert result[0]["amount"] == "6500.00"
    assert validate_candidates({"candidates": [{**candidate, "amount": "NaN"}]}, page, set()) == []
    assert (
        validate_candidates(
            {"candidates": [{**candidate, "excerpt": "Base Bid $7,000"}]}, page, set()
        )
        == []
    )


def test_ai_candidate_classifies_commercial_permit_without_reclassifying_scope():
    text = "Mechanical permit included. Supply and install HVAC ductwork."
    page = [{"page_number": 1, "text": text}]
    common = {
        "amount": None,
        "currency": None,
        "treatment": None,
        "scope_item_id": None,
        "included_in_base_bid": None,
        "page_number": 1,
    }
    permit = {
        **common,
        "kind": "scope_coverage",
        "title": "Mechanical permit",
        "description": "Mechanical permit included.",
        "excerpt": "Mechanical permit included.",
    }
    construction_scope = {
        **common,
        "kind": "scope_coverage",
        "title": "HVAC ductwork",
        "description": "Supply and install HVAC ductwork.",
        "excerpt": "Supply and install HVAC ductwork.",
    }

    result = validate_candidates({"candidates": [permit, construction_scope]}, page, set())

    assert result[0]["kind"] == "fee"
    assert result[0]["treatment"] == "included"
    assert result[1]["kind"] == "scope_coverage"
    assert result[1]["treatment"] is None


def test_ai_candidate_preserves_allowance_inclusion_and_separates_lead_time_from_schedule():
    text = (
        "Controls Allowance CAD 5,000.00 Included in Base Bid\n"
        "Equipment lead time is 14 weeks.\n"
        "Schedule: 5 weeks from mobilization"
    )
    page = [{"page_number": 1, "text": text}]
    common = {
        "amount": None,
        "currency": None,
        "treatment": None,
        "scope_item_id": None,
        "included_in_base_bid": None,
        "page_number": 1,
    }
    allowance = {
        **common,
        "kind": "allowance",
        "title": "Controls Allowance",
        "description": "Controls allowance",
        "amount": "5000",
        "currency": "CAD",
        "excerpt": "Controls Allowance CAD 5,000.00 Included in Base Bid",
    }
    lead_time = {
        **common,
        "kind": "schedule",
        "title": "Equipment lead time",
        "description": "Equipment lead time is 14 weeks.",
        "excerpt": "Equipment lead time is 14 weeks.",
    }
    schedule = {
        **common,
        "kind": "schedule",
        "title": "Schedule",
        "description": "5 weeks from mobilization",
        "excerpt": "Schedule: 5 weeks from mobilization",
    }

    result = validate_candidates({"candidates": [allowance, lead_time, schedule]}, page, {998})

    assert result[0]["kind"] == "allowance"
    assert result[0]["amount"] == "5000.00"
    assert result[0]["currency"] == "CAD"
    assert result[0]["included_in_base_bid"] is True
    assert result[1]["kind"] == "condition"
    assert result[2]["kind"] == "schedule"
    assert all(candidate["scope_item_id"] is None for candidate in result)


def test_accepting_allowance_candidate_preserves_included_in_base(
    setup, user, storage, monkeypatch
):
    _, submission = source(setup, user)
    revision = create_revision(submission=submission, actor=user)
    run = BidExtractionRun.objects.create(
        submission=submission,
        attachment=submission.attachments.first(),
        requested_by=user,
        provider="openai",
        model="gpt-5-mini",
        schema_version=3,
        status="succeeded",
        candidates=[
            {
                "kind": "allowance",
                "title": "Controls Allowance",
                "description": "Controls allowance",
                "amount": "5000.00",
                "currency": "CAD",
                "treatment": "allowance",
                "scope_item_id": None,
                "included_in_base_bid": True,
                "page_number": 1,
                "excerpt": "Controls Allowance CAD 5,000.00 Included in Base Bid",
            }
        ],
    )
    monkeypatch.setattr(
        "apps.outreach.bid_extraction.quote_pages",
        lambda _: [
            {
                "page_number": 1,
                "text": "Controls Allowance CAD 5,000.00 Included in Base Bid",
            }
        ],
    )

    decision = decide_candidate(
        run=run, revision=revision, actor=user, index=0, decision="accepted"
    )

    assert decision.commercial_item.kind == "allowance"
    assert decision.commercial_item.amount == Decimal("5000.00")
    assert decision.commercial_item.currency == "CAD"
    assert decision.commercial_item.included_in_base == "yes"


def test_confirmed_summary_candidates_map_currency_validity_and_schedule_without_duplicates(
    setup, user, storage, monkeypatch
):
    _, submission = source(setup, user)
    revision = create_revision(submission=submission, actor=user)
    excerpt = {
        "base_bid": "Base Bid: CAD 176,500.00",
        "validity": "Bid Validity: 21 days",
        "schedule": "Schedule: 5 weeks from mobilization",
        "condition": "Equipment lead time is 14 weeks.",
    }
    candidates = [
        {
            "kind": kind,
            "title": title,
            "description": description,
            "amount": amount,
            "currency": currency,
            "treatment": None,
            "scope_item_id": None,
            "included_in_base_bid": None,
            "page_number": 1,
            "excerpt": excerpt[kind],
        }
        for kind, title, description, amount, currency in (
            ("base_bid", "Base Bid", "Base bid amount", "176500.00", "CAD"),
            ("validity", "Bid Validity", "Bid validity period", None, None),
            ("schedule", "Schedule", "Work schedule", None, None),
            ("condition", "Equipment lead time", "Equipment lead time", None, None),
        )
    ]
    run = BidExtractionRun.objects.create(
        submission=submission,
        attachment=submission.attachments.first(),
        requested_by=user,
        provider="openai",
        model="gpt-5-mini",
        schema_version=3,
        status="succeeded",
        candidates=candidates,
    )
    monkeypatch.setattr(
        "apps.outreach.bid_extraction.quote_pages",
        lambda _: [{"page_number": 1, "text": "\n".join(excerpt.values())}],
    )

    for index in range(len(candidates)):
        decide_candidate(run=run, revision=revision, actor=user, index=index, decision="accepted")

    revision.refresh_from_db()
    assert revision.base_bid == Decimal("176500.00")
    assert revision.currency == "CAD"
    assert revision.currency_review == "confirmed"
    assert revision.validity_days == 21
    assert revision.schedule_text == "5 weeks from mobilization"
    assert list(revision.commercial_items.values_list("title", flat=True)) == [
        "Equipment lead time"
    ]
    assert set(revision.evidence.values_list("field_key", flat=True)) == {
        "base_bid",
        "currency",
        "validity_days",
        "schedule_text",
        "",
    }


def test_viewer_reads_revision_but_cannot_structure_or_ready(
    setup, user, organization, membership, storage
):
    project, submission = source(setup, user)
    url = reverse(
        "bid-revision-list",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": project.pk,
            "submission_pk": submission.pk,
        },
    )
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.post(url, {"contractor_label": "Original"}, format="json").status_code == 201
    membership.role = "viewer"
    membership.save()
    assert client.get(url).status_code == 200
    assert client.post(url, {}, format="json").status_code == 403
    revision = BidRevision.objects.first()
    ready_url = reverse(
        "bid-revision-ready",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": project.pk,
            "submission_pk": submission.pk,
            "revision_pk": revision.pk,
        },
    )
    assert client.post(ready_url).status_code == 403


def test_inactive_membership_and_wrong_project_cannot_access_bid_revision(
    setup, user, organization, membership, storage
):
    project, submission = source(setup, user)
    url = reverse(
        "bid-revision-list",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": project.pk,
            "submission_pk": submission.pk,
        },
    )
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.get(url).status_code == 200
    wrong = reverse(
        "bid-revision-list",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": project.pk + 999,
            "submission_pk": submission.pk,
        },
    )
    assert client.get(wrong).status_code == 404
    membership.is_active = False
    membership.save()
    assert client.get(url).status_code == 403
    assert client.post(url, {}, format="json").status_code == 403


def test_archived_project_can_read_history_but_cannot_create_revision(setup, user, storage):
    project, submission = source(setup, user)
    project.is_active = False
    project.save()
    with pytest.raises(ValidationError):
        create_revision(submission=submission, actor=user)
    assert BidRevision.objects.filter(project=project).count() == 0


def test_explicit_mocked_real_provider_proposal_is_evidence_grounded_and_not_ready(
    setup, user, storage, monkeypatch, settings
):
    _, submission = source(setup, user)
    revision = create_revision(submission=submission, actor=user)
    settings.AI_PROVIDER_CLASS = "apps.analysis.providers.OpenAIAnalysisProvider"
    settings.AI_MODEL = "gpt-5-mini"
    pages = [{"page_number": 1, "text": "Base Bid $6,500. Tax extra."}]
    monkeypatch.setattr("apps.outreach.bid_extraction.quote_pages", lambda attachment: pages)
    requests = []
    monkeypatch.setattr(
        "apps.outreach.bid_extraction.process_bid_extraction.delay",
        lambda run_id: requests.append(run_id),
    )
    output = {
        "candidates": [
            {
                "kind": "base_bid",
                "title": "Base Bid",
                "description": "Quoted",
                "amount": "6500",
                "currency": "CAD",
                "treatment": None,
                "scope_item_id": None,
                "included_in_base_bid": None,
                "page_number": 1,
                "excerpt": "Base Bid $6,500",
            },
            {
                "kind": "base_bid",
                "title": "Invalid quote",
                "description": "Unsupported",
                "amount": "7000",
                "currency": "CAD",
                "treatment": None,
                "scope_item_id": None,
                "included_in_base_bid": None,
                "page_number": 1,
                "excerpt": "Base Bid $7,000",
            },
        ]
    }
    calls = []

    def provider(self, *, model, system_prompt, input_payload, schema, image_data_url=None):
        del self, system_prompt, image_data_url
        calls.append((model, input_payload["quote_pages"], schema["required"]))
        return ProviderResult(output, "mock-request", {"total_tokens": 10})

    monkeypatch.setattr("apps.outreach.bid_extraction.OpenAIAnalysisProvider.analyze", provider)
    attachment = submission.attachments.first()
    run = request_extraction(
        attachment=attachment, actor=user, request_key="7103e48b-388e-4be6-b8c6-355057513380"
    )
    assert run.status == "queued" and calls == []
    assert (
        request_extraction(
            attachment=attachment, actor=user, request_key="7103e48b-388e-4be6-b8c6-355057513380"
        ).pk
        == run.pk
    )
    assert BidExtractionRun.objects.count() == 1
    process_bid_extraction(run.pk)  # Network boundary remains mocked.
    run.refresh_from_db()
    assert run.status == "succeeded" and len(run.candidates) == 1
    assert run.candidates[0]["amount"] == "6500.00"
    assert calls[0][0] == "gpt-5-mini"
    revision.refresh_from_db()
    assert revision.status == "draft" and revision.base_bid is None
    ignored = decide_candidate(run=run, revision=revision, actor=user, index=0, decision="ignored")
    assert ignored.pk and revision.base_bid is None
    assert (
        decide_candidate(run=run, revision=revision, actor=user, index=0, decision="ignored").pk
        == ignored.pk
    )
    assert BidCandidateDecision.objects.count() == 1
    assert submission.attachments.count() == 1


def test_human_candidate_correction_is_a_draft_decision_with_exact_quote_evidence(
    setup, user, storage, monkeypatch
):
    _, submission = source(setup, user)
    revision = create_revision(submission=submission, actor=user)
    attachment = submission.attachments.first()
    candidate = {
        "kind": "base_bid",
        "title": "Base Bid",
        "description": "Quoted",
        "amount": "6500.00",
        "currency": "CAD",
        "treatment": None,
        "scope_item_id": None,
        "included_in_base_bid": None,
        "page_number": 1,
        "excerpt": "Base Bid $6,500.01",
    }
    monkeypatch.setattr(
        "apps.outreach.bid_extraction.quote_pages",
        lambda _: [{"page_number": 1, "text": "Base Bid $6,500.01"}],
    )
    run = BidExtractionRun.objects.create(
        submission=submission,
        attachment=attachment,
        requested_by=user,
        provider="openai",
        model="gpt-5-mini",
        status="succeeded",
        candidates=[candidate],
        completed_at=timezone.now(),
    )
    decision = decide_candidate(
        run=run,
        revision=revision,
        actor=user,
        index=0,
        decision="corrected",
        corrections={"amount": "6500.01", "note": "Corrected cents from quote"},
    )
    revision.refresh_from_db()
    assert revision.base_bid == Decimal("6500.01")
    assert revision.status == "draft" and revision.base_bid_review == "confirmed"
    assert decision.evidence.attachment_id == attachment.pk
    assert decision.evidence.page_number == 1
    assert decision.evidence.excerpt == "Base Bid $6,500.01"
    with pytest.raises(ValidationError):
        decide_candidate(run=run, revision=revision, actor=user, index=1, decision="accepted")


def test_ready_items_and_scope_decisions_cannot_be_rewritten(setup, user, storage):
    _, submission = source(setup, user)
    revision = create_revision(submission=submission, actor=user)
    item = save_commercial_item(
        revision=revision,
        actor=user,
        values={
            "kind": "alternate",
            "title": "Extra work",
            "treatment": "add",
            "amount": "100",
            "currency": "CAD",
        },
    )
    scope_item = ScopeItem.objects.create(
        package_version=submission.scope_version,
        item_key="test-wire",
        item_type="general",
        responsibility="unclear",
        title="Wiring",
        description="Test",
        sequence=1,
    )
    coverage = save_scope_coverage(
        revision=revision,
        actor=user,
        scope_item=scope_item,
        state="not_addressed",
        reviewed=True,
    )
    save_summary(
        revision=revision,
        actor=user,
        values={
            "base_bid": None,
            "base_bid_review": "not_stated",
            "currency_review": "not_stated",
            "tax_reviewed": True,
            "commercial_items_reviewed": True,
            "scope_reviewed": True,
        },
    )
    mark_ready(revision=revision, actor=user)
    item.title = "Rewritten"
    with pytest.raises(ValidationError):
        item.save()
    with pytest.raises(ValidationError):
        item.delete()
    coverage.state = "excluded"
    with pytest.raises(ValidationError):
        coverage.save()
    assert submission.attachments.count() == 1


def test_provider_failure_preserves_original_quote_and_no_commercial_truth(
    setup, user, storage, monkeypatch
):
    _, submission = source(setup, user)
    attachment = submission.attachments.first()
    run = BidExtractionRun.objects.create(
        submission=submission,
        attachment=attachment,
        requested_by=user,
        provider="openai",
        model="gpt-5-mini",
    )
    monkeypatch.setattr(
        "apps.outreach.bid_extraction.quote_pages",
        lambda _: [{"page_number": 1, "text": "Base Bid $6,500"}],
    )

    def fail(self, **kwargs):
        del self, kwargs
        raise ProviderFailure("provider_timeout", "The AI provider request timed out.")

    monkeypatch.setattr("apps.outreach.bid_extraction.OpenAIAnalysisProvider.analyze", fail)
    process_bid_extraction(run.pk)
    run.refresh_from_db()
    assert run.status == "failed" and run.safe_error_code == "provider_timeout"
    assert run.candidates == [] and BidRevision.objects.count() == 0
    assert submission.attachments.count() == 1


def test_post_response_validation_failure_retains_safe_provider_usage(
    setup, user, storage, monkeypatch
):
    _, submission = source(setup, user)
    run = BidExtractionRun.objects.create(
        submission=submission,
        attachment=submission.attachments.first(),
        requested_by=user,
        provider="openai",
        model="gpt-5-mini",
    )
    monkeypatch.setattr(
        "apps.outreach.bid_extraction.quote_pages",
        lambda _: [{"page_number": 1, "text": "Base Bid $6,500"}],
    )

    def malformed(self, **kwargs):
        del self, kwargs
        return ProviderResult({"wrong": []}, "mock-request-123", {"total_tokens": 42})

    monkeypatch.setattr("apps.outreach.bid_extraction.OpenAIAnalysisProvider.analyze", malformed)
    process_bid_extraction(run.pk)
    run.refresh_from_db()
    assert run.status == "failed"
    assert run.request_id == "mock-request-123" and run.usage["total_tokens"] == 42
    assert run.candidates == [] and BidRevision.objects.count() == 0
