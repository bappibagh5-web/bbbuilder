import hashlib
import io
import json
import urllib.error
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymupdf
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import override_settings
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
    ProjectIntelligenceSnapshotProvenance,
)
from apps.analysis.providers import (
    FakeAnalysisProvider,
    OpenAIAnalysisProvider,
    ProviderFailure,
    ProviderResult,
)
from apps.analysis.rendering import PageRenderFailure, render_page_data_url
from apps.analysis.sanitization import sanitize_provider_value
from apps.analysis.schemas import validate_result
from apps.analysis.services import (
    _claim_run,
    _grounded_excerpt,
    approve_intelligence_snapshot,
    create_intelligence_snapshot,
    detect_conflicts,
    dispatch_analysis_run,
    execute_analysis_run,
    materialize_findings,
    recover_stale_analysis_runs,
    request_analysis_run,
    resolve_conflict,
    retry_analysis_run,
    review_finding,
    snapshot_freshness,
    snapshot_readiness,
)
from apps.documents.models import (
    Document,
    DocumentPage,
    DocumentRevision,
    DrawingSheet,
    FileAsset,
    ProjectFile,
)
from apps.documents.services import set_document_active
from apps.organizations.models import Membership, Organization
from apps.processing.models import ProcessingJob
from apps.projects.models import AuditEvent, Project

pytestmark = pytest.mark.django_db


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-AI-001",
        name="AI Test",
        project_timezone="America/Vancouver",
        status=Project.Status.DOCUMENTS_UPLOADED,
    )


@pytest.fixture
def revision(project, user):
    content = b"%PDF-1.4 analysis test"
    asset = FileAsset.objects.create(
        organization=project.organization,
        bucket="test",
        storage_key="analysis/source.pdf",
        original_filename="source.pdf",
        declared_mime_type="application/pdf",
        detected_mime_type="application/pdf",
        byte_size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        created_by=user,
    )
    project_file = ProjectFile.objects.create(project=project, file_asset=asset, created_by=user)
    document = Document.objects.create(
        project=project, title="Drawing Set", category=Document.Category.DRAWINGS, created_by=user
    )
    revision = DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        revision_label="R1",
        source_filename="source.pdf",
        created_by=user,
    )
    page1 = DocumentPage.objects.create(
        document_revision=revision,
        page_number=1,
        page_label="1",
        width_points=612,
        height_points=792,
        native_text="Bid closes September 15.",
        native_text_char_count=24,
        has_native_text=True,
        parser_name="PyMuPDF",
        parser_version="1.28.2",
    )
    page2 = DocumentPage.objects.create(
        document_revision=revision,
        page_number=2,
        page_label="M01",
        width_points=792,
        height_points=612,
        native_text="M01 MECHANICAL PLAN",
        native_text_char_count=19,
        has_native_text=True,
        parser_name="PyMuPDF",
        parser_version="1.28.2",
    )
    DrawingSheet.objects.create(
        page=page2,
        sheet_number="M01",
        sheet_title="MECHANICAL PLAN",
        extraction_method=DrawingSheet.ExtractionMethod.NATIVE_TEXT,
        quality=DrawingSheet.Quality.HIGH,
    )
    for job_type in (ProcessingJob.JobType.SOURCE_VERIFICATION, ProcessingJob.JobType.PDF_INDEXING):
        ProcessingJob.objects.create(
            document_revision=revision,
            job_type=job_type,
            status=ProcessingJob.Status.SUCCEEDED,
            requested_by=user,
            finished_at=page1.indexed_at,
        )
    return revision


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def list_url(revision, *, organization=None, project=None, document=None):
    return reverse(
        "revision-analysis-run-list",
        kwargs={
            "organization_slug": (organization or revision.document.project.organization).slug,
            "project_pk": (project or revision.document.project).pk,
            "document_pk": (document or revision.document).pk,
            "revision_pk": revision.pk,
        },
    )


def valid_page_result(page):
    sheet = getattr(page, "drawing_sheet", None)
    return {
        "page_type_candidate": "drawing",
        "summary": "Supported summary",
        "candidates": [
            {
                "category": "scope_trade",
                "subject": "Mechanical",
                "value": "Mechanical work is shown.",
                "support": "explicit",
                "evidence": [
                    {
                        "document_page_id": page.pk,
                        "page_number": page.page_number,
                        "drawing_sheet_id": sheet.pk if sheet else None,
                        "sheet_number": sheet.sheet_number if sheet else "",
                        "evidence_excerpt": page.native_text if page.has_native_text else "",
                        "visual_evidence_description": "",
                    }
                ],
            }
        ],
        "open_questions": [],
    }


class RecordingProvider:
    calls = []

    def analyze(self, **kwargs):
        self.calls.append(kwargs)
        payload = kwargs["input_payload"]
        if payload["task_type"] == "page_analysis":
            page_id = payload["page"]["document_page_id"]
            page = DocumentPage.objects.get(pk=page_id)
            return ProviderResult(
                valid_page_result(page),
                f"page-{page_id}",
                {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
            )
        candidates = [
            candidate
            for item in payload["page_results"]
            for candidate in item["result"]["candidates"]
        ]
        return ProviderResult(
            {
                "document_type_candidate": "drawings",
                "document_summary": "Drawing set summary",
                "candidates": candidates,
                "unresolved_questions": [],
            },
            "synthesis",
            {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        )


def test_provider_value_sanitizer_is_recursive_and_null_only():
    original = {
        "plain": "unchanged",
        "normal_unicode": "Mécanique — 温度",
        "nested": {
            "multiple": "before\x00middle\x00after",
            "items": ["one\x00two", 7, None, {"deep": "\x00"}],
        },
    }

    sanitized = sanitize_provider_value(original)

    assert sanitized == {
        "plain": "unchanged",
        "normal_unicode": "Mécanique — 温度",
        "nested": {
            "multiple": "before�middle�after",
            "items": ["one�two", 7, None, {"deep": "�"}],
        },
    }
    assert original["nested"]["multiple"] == "before\x00middle\x00after"


class NullCharacterProvider:
    def analyze(self, **kwargs):
        payload = kwargs["input_payload"]
        if payload["task_type"] == "page_analysis":
            page = DocumentPage.objects.get(pk=payload["page"]["document_page_id"])
            result = valid_page_result(page)
            result["summary"] = "Résumé \x00 unchanged Unicode — 温度"
            result["candidates"][0]["value"] = "Supply\x00and\x00install"
            result["candidates"][0]["evidence"][0]["evidence_excerpt"] = (
                "PROVIDE & INSTALL\x00NEW WORK"
            )
            return ProviderResult(
                result,
                "request\x00id",
                {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
            )
        candidates = [
            candidate
            for item in payload["page_results"]
            for candidate in item["result"]["candidates"]
        ]
        return ProviderResult(
            {
                "document_type_candidate": "drawings",
                "document_summary": "Combined\x00summary",
                "candidates": candidates,
                "unresolved_questions": ["Confirm\x00scope"],
            },
            "synthesis\x00request",
            {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        )


@override_settings(AI_PROVIDER_CLASS="tests.test_analysis.NullCharacterProvider")
@patch(
    "apps.analysis.services.render_page_data_url",
    return_value=("data:image/png;base64,eA==", {}),
)
def test_null_characters_are_sanitized_before_page_and_synthesis_persistence(
    render, revision, user
):
    original_page_text = list(revision.pages.order_by("id").values_list("id", "native_text"))
    original_checksum = revision.project_file.file_asset.checksum

    run = request_analysis_run(revision=revision, requested_by=user)
    assert execute_analysis_run(run.pk) == {"outcome": "succeeded"}
    run.refresh_from_db()
    tasks = list(run.task_runs.select_related("document_page").order_by("id"))

    assert run.status == AnalysisRun.Status.SUCCEEDED
    assert all(task.status == AnalysisTaskRun.Status.SUCCEEDED for task in tasks)
    assert "\x00" not in json.dumps(run.result_summary, ensure_ascii=False)
    assert run.result_summary["document_summary"] == "Combined�summary"
    assert run.result_summary["unresolved_questions"] == ["Confirm�scope"]
    page_task = tasks[0]
    assert page_task.structured_result["summary"] == "Résumé � unchanged Unicode — 温度"
    assert page_task.structured_result["candidates"][0]["value"] == ("Supply�and�install")
    evidence = page_task.structured_result["candidates"][0]["evidence"][0]
    assert evidence["evidence_excerpt"] == "PROVIDE & INSTALL�NEW WORK"
    assert evidence["document_page_id"] == page_task.document_page_id
    assert evidence["page_number"] == page_task.document_page.page_number
    assert page_task.provider_request_id == "request�id"
    assert tasks[-1].provider_request_id == "synthesis�request"
    assert list(revision.pages.order_by("id").values_list("id", "native_text")) == (
        original_page_text
    )
    revision.project_file.file_asset.refresh_from_db()
    assert revision.project_file.file_asset.checksum == original_checksum


@override_settings(AI_PROVIDER_CLASS="tests.test_analysis.RecordingProvider")
@patch(
    "apps.analysis.services.render_page_data_url",
    return_value=("data:image/png;base64,eA==", {}),
)
def test_explicit_analysis_builds_page_tasks_and_synthesis(render, revision, user):
    RecordingProvider.calls = []
    run = request_analysis_run(revision=revision, requested_by=user)
    assert run.task_runs.count() == 3
    assert list(run.task_runs.values_list("input_mode", flat=True)) == [
        "native_text",
        "native_text_vision",
        "structured_page_results",
    ]
    assert (
        revision.document.project.__class__.objects.get(pk=revision.document.project_id).status
        == Project.Status.AI_ANALYSIS
    )
    assert execute_analysis_run(run.pk) == {"outcome": "succeeded"}
    render.assert_called_once()
    run.refresh_from_db()
    assert run.status == AnalysisRun.Status.SUCCEEDED
    assert run.result_summary["document_summary"] == "Drawing set summary"
    assert run.usage_metadata == {
        "input_tokens": 7,
        "output_tokens": 4,
        "total_tokens": 11,
        "request_count": 3,
        "vision_page_count": 1,
    }
    assert AuditEvent.objects.filter(
        action_code="analysis.requested", target_id=str(run.pk)
    ).exists()
    assert AuditEvent.objects.filter(
        action_code="analysis.completed", target_id=str(run.pk)
    ).exists()


def test_run_history_and_ownership_are_immutable(revision, user):
    first = request_analysis_run(revision=revision, requested_by=user)
    AnalysisRun.objects.filter(pk=first.pk).update(status=AnalysisRun.Status.SUCCEEDED)
    second = request_analysis_run(revision=revision, requested_by=user, predecessor=first)
    assert first.pk != second.pk
    second.document_revision = DocumentRevision.objects.none().first()
    with pytest.raises((ValidationError, ValueError)):
        second.save()


def test_one_active_run_and_cross_revision_page_rejected(revision, user, project):
    run = request_analysis_run(revision=revision, requested_by=user)
    with pytest.raises(ValidationError):
        request_analysis_run(revision=revision, requested_by=user)
    other_asset = FileAsset.objects.create(
        organization=project.organization,
        bucket="test",
        storage_key="analysis/other.pdf",
        original_filename="other.pdf",
        declared_mime_type="application/pdf",
        detected_mime_type="application/pdf",
        byte_size=1,
        checksum=hashlib.sha256(b"x").hexdigest(),
        created_by=user,
    )
    other_pf = ProjectFile.objects.create(project=project, file_asset=other_asset, created_by=user)
    other_doc = Document.objects.create(project=project, title="Other", created_by=user)
    other_revision = DocumentRevision.objects.create(
        document=other_doc, project_file=other_pf, source_filename="other.pdf", created_by=user
    )
    other_page = DocumentPage.objects.create(
        document_revision=other_revision,
        page_number=1,
        width_points=1,
        height_points=1,
        native_text="",
        native_text_char_count=0,
        has_native_text=False,
        parser_name="test",
        parser_version="1",
    )
    task = AnalysisTaskRun(
        analysis_run=run,
        document_page=other_page,
        task_type="page_analysis",
        input_mode="vision",
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
    )
    with pytest.raises(ValidationError):
        task.save()


@pytest.mark.parametrize("missing", ["source", "index", "pages"])
def test_prerequisites_are_enforced(revision, user, missing):
    if missing == "source":
        ProcessingJob.objects.filter(
            document_revision=revision, job_type="source_verification"
        ).delete()
    if missing == "index":
        ProcessingJob.objects.filter(document_revision=revision, job_type="pdf_indexing").delete()
    if missing == "pages":
        DrawingSheet.objects.filter(page__document_revision=revision).delete()
        DocumentPage.objects.filter(document_revision=revision).delete()
    with pytest.raises(ValidationError):
        request_analysis_run(revision=revision, requested_by=user)
    assert (
        revision.document.project.__class__.objects.get(pk=revision.document.project_id).status
        == Project.Status.DOCUMENTS_UPLOADED
    )


def test_unsupported_non_pdf_is_rejected(revision, user):
    FileAsset.objects.filter(pk=revision.project_file.file_asset_id).update(
        declared_mime_type="text/plain", detected_mime_type="text/plain"
    )
    revision.refresh_from_db()
    with pytest.raises(ValidationError):
        request_analysis_run(revision=revision, requested_by=user)


class InvalidProvider:
    def analyze(self, **kwargs):
        return ProviderResult({"not": "the schema"})


@override_settings(AI_PROVIDER_CLASS="tests.test_analysis.InvalidProvider")
def test_invalid_structured_output_fails_without_persisting_result(revision, user):
    run = request_analysis_run(revision=revision, requested_by=user)
    execute_analysis_run(run.pk)
    run.refresh_from_db()
    assert run.status == "failed" and run.failure_code == "invalid_structured_response"
    assert not run.result_summary
    assert run.task_runs.filter(status="failed", structured_result={}).exists()


class TimeoutProvider:
    calls = 0

    def analyze(self, **kwargs):
        self.calls += 1
        raise ProviderFailure(
            "provider_timeout", "The AI provider request timed out.", transient=True
        )


@override_settings(AI_PROVIDER_CLASS="tests.test_analysis.TimeoutProvider", AI_TASK_MAX_ATTEMPTS=2)
@patch(
    "apps.analysis.services.render_page_data_url",
    return_value=("data:image/png;base64,eA==", {}),
)
def test_transient_retry_is_bounded_and_retry_creates_new_run(render, revision, user):
    provider = TimeoutProvider()
    provider.calls = 0
    with patch("apps.analysis.services.get_analysis_provider", return_value=provider):
        run = request_analysis_run(revision=revision, requested_by=user)
        first = execute_analysis_run(run.pk)
        second = execute_analysis_run(run.pk)
    run.refresh_from_db()
    assert first == {
        "outcome": "retry",
        "countdown": 30,
        "error_code": "provider_timeout",
    }
    assert second == {"outcome": "failed", "error_code": "provider_timeout"}
    assert run.status == "failed" and provider.calls == 2
    replacement = retry_analysis_run(run=run, requested_by=user)
    assert replacement.predecessor_id == run.pk and run.status == "failed"


def test_operator_api_can_request_viewer_can_only_read(revision, user, membership):
    response = client_for(user).post(list_url(revision), {}, format="json")
    assert response.status_code == 201
    viewer = get_user_model().objects.create_user(email="viewer@example.com", password="pass")
    Membership.objects.create(
        user=viewer,
        organization=revision.document.project.organization,
        role=Membership.Role.VIEWER,
    )
    assert client_for(viewer).get(list_url(revision)).status_code == 200
    assert client_for(viewer).post(list_url(revision), {}, format="json").status_code == 403
    assert client_for(viewer).delete(list_url(revision)).status_code == 405


def test_api_denies_unauthenticated_inactive_and_cross_document_context(revision, user, membership):
    assert APIClient().get(list_url(revision)).status_code in (401, 403)
    other_document = Document.objects.create(
        project=revision.document.project,
        title="Unrelated document",
        created_by=user,
    )
    assert client_for(user).get(list_url(revision, document=other_document)).status_code == 404
    membership.is_active = False
    membership.save(update_fields=("is_active",))
    assert client_for(user).get(list_url(revision)).status_code == 403


def test_api_exposes_safe_input_manifest_only(revision, user, membership):
    run = request_analysis_run(revision=revision, requested_by=user)
    response = client_for(user).get(list_url(revision))
    assert response.status_code == 200
    manifest = response.data[0]["input_manifest"]
    assert manifest["document_revision_id"] == revision.pk
    assert "checksum" not in manifest and "file_asset_id" not in manifest
    detail_url = reverse(
        "analysis-run-detail",
        kwargs={
            "organization_slug": revision.document.project.organization.slug,
            "project_pk": revision.document.project_id,
            "run_pk": run.pk,
        },
    )
    assert client_for(user).delete(detail_url).status_code == 405


def test_cross_organization_and_project_are_isolated(revision, user):
    other_org = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(user=user, organization=other_org, role=Membership.Role.ADMIN)
    other_project = Project.objects.create(
        organization=other_org,
        created_by=user,
        project_number="OTHER-1",
        name="Other",
        project_timezone="UTC",
    )
    assert client_for(user).get(list_url(revision, organization=other_org)).status_code == 404
    assert (
        client_for(user)
        .get(list_url(revision, organization=other_org, project=other_project))
        .status_code
        == 404
    )


def test_later_project_status_does_not_regress(revision, user):
    Project.objects.filter(pk=revision.document.project_id).update(
        status=Project.Status.HUMAN_SCOPE_REVIEW
    )
    request_analysis_run(revision=revision, requested_by=user)
    assert (
        Project.objects.get(pk=revision.document.project_id).status
        == Project.Status.HUMAN_SCOPE_REVIEW
    )


def test_image_only_page_routes_to_vision(revision, user):
    DocumentPage.objects.create(
        document_revision=revision,
        page_number=3,
        width_points=612,
        height_points=792,
        native_text="",
        native_text_char_count=0,
        has_native_text=False,
        parser_name="PyMuPDF",
        parser_version="1.28.2",
    )
    run = request_analysis_run(revision=revision, requested_by=user)
    modes = list(
        run.task_runs.filter(task_type="page_analysis").values_list("input_mode", flat=True)
    )
    assert modes == ["native_text", "native_text_vision", "vision"]


class ReadStorage:
    def __init__(self, content):
        self.content = content

    def open(self, key):
        return io.BytesIO(self.content)


def test_exact_page_render_is_bounded_and_temp_files_are_cleaned(revision):
    pdf = pymupdf.open()
    pdf.new_page(width=2000, height=1000).insert_text((40, 40), "PAGE ONE")
    pdf.new_page(width=1000, height=2000).insert_text((40, 40), "PAGE TWO")
    content = pdf.tobytes()
    pdf.close()
    page = revision.pages.get(page_number=2)
    temporary_paths = []
    import tempfile

    original = tempfile.NamedTemporaryFile

    def tracked_temp(*args, **kwargs):
        result = original(*args, **kwargs)
        temporary_paths.append(result.name)
        return result

    with (
        patch("apps.analysis.rendering.get_object_storage", return_value=ReadStorage(content)),
        patch("apps.analysis.rendering.tempfile.NamedTemporaryFile", side_effect=tracked_temp),
        override_settings(AI_RENDER_MAX_DIMENSION=500),
    ):
        data_url, metadata = render_page_data_url(page)
    assert data_url.startswith("data:image/png;base64,")
    assert max(metadata["render_width"], metadata["render_height"]) <= 500
    assert temporary_paths and all(not Path(path).exists() for path in temporary_paths)


@pytest.mark.parametrize("mode", ["timeout", "permanent_failure"])
def test_rendered_source_is_cleaned_before_provider_failure(mode, revision, user):
    pdf = pymupdf.open()
    pdf.new_page().insert_text((40, 40), "PAGE ONE")
    pdf.new_page().insert_text((40, 40), "PAGE TWO")
    content = pdf.tobytes()
    pdf.close()
    page = revision.pages.get(page_number=1)
    DocumentPage.objects.filter(pk=page.pk).update(
        has_native_text=False, native_text="", native_text_char_count=0
    )
    temporary_paths = []
    import tempfile

    original = tempfile.NamedTemporaryFile

    def tracked_temp(*args, **kwargs):
        result = original(*args, **kwargs)
        temporary_paths.append(result.name)
        return result

    with (
        patch("apps.analysis.rendering.get_object_storage", return_value=ReadStorage(content)),
        patch("apps.analysis.rendering.tempfile.NamedTemporaryFile", side_effect=tracked_temp),
        override_settings(
            AI_PROVIDER_CLASS="apps.analysis.providers.FakeAnalysisProvider",
            AI_FAKE_MODE=mode,
        ),
    ):
        run = request_analysis_run(revision=revision, requested_by=user)
        outcome = execute_analysis_run(run.pk)["outcome"]
    assert outcome == ("retry" if mode == "timeout" else "failed")
    assert temporary_paths and all(not Path(path).exists() for path in temporary_paths)


def test_render_failure_cleans_temporary_source(revision):
    page = revision.pages.get(page_number=2)
    temporary_paths = []
    import tempfile

    original = tempfile.NamedTemporaryFile

    def tracked_temp(*args, **kwargs):
        result = original(*args, **kwargs)
        temporary_paths.append(result.name)
        return result

    with (
        patch(
            "apps.analysis.rendering.get_object_storage",
            return_value=ReadStorage(b"not a valid PDF"),
        ),
        patch("apps.analysis.rendering.tempfile.NamedTemporaryFile", side_effect=tracked_temp),
        pytest.raises(PageRenderFailure),
    ):
        render_page_data_url(page)
    assert temporary_paths and all(not Path(path).exists() for path in temporary_paths)


@pytest.mark.parametrize(
    ("mode", "code", "transient"),
    [
        ("timeout", "provider_timeout", True),
        ("rate_limit", "provider_rate_limited", True),
        ("unavailable", "provider_unavailable", True),
        ("permanent_failure", "analysis_failed", False),
    ],
)
def test_fake_provider_controlled_failures(mode, code, transient):
    with override_settings(AI_FAKE_MODE=mode), pytest.raises(ProviderFailure) as captured:
        FakeAnalysisProvider().analyze(
            model="fake",
            system_prompt="final JSON only",
            input_payload={"task_type": "page_analysis", "page": {}},
            schema={},
        )
    assert captured.value.code == code
    assert captured.value.transient is transient


def test_fake_provider_supports_absent_usage():
    with override_settings(AI_FAKE_MODE="success", AI_FAKE_INCLUDE_USAGE=False):
        result = FakeAnalysisProvider().analyze(
            model="fake",
            system_prompt="final JSON only",
            input_payload={
                "task_type": "page_analysis",
                "page": {
                    "document_page_id": 1,
                    "page_number": 1,
                    "sheet_number": "",
                    "native_text": "",
                },
            },
            schema={},
        )
    assert result.usage is None


def test_fake_provider_returns_valid_exact_page_evidence():
    result = FakeAnalysisProvider().analyze(
        model="fake",
        system_prompt="final JSON only",
        input_payload={
            "task_type": "page_analysis",
            "page": {
                "document_page_id": 42,
                "page_number": 3,
                "drawing_sheet_id": 9,
                "sheet_number": "M101",
                "native_text": "M101 MECHANICAL PLAN",
            },
        },
        schema={},
    )
    validated = validate_result("page_analysis", result.structured_output)
    evidence = validated["candidates"][0]["evidence"][0]
    assert evidence["document_page_id"] == 42
    assert evidence["page_number"] == 3
    assert evidence["drawing_sheet_id"] == 9
    assert evidence["sheet_number"] == "M101"


@pytest.mark.parametrize(
    ("side_effect", "code", "transient"),
    [
        (TimeoutError(), "provider_timeout", True),
        (urllib.error.URLError("offline"), "provider_unavailable", True),
        (
            urllib.error.HTTPError("https://api.openai.com", 429, "rate", {}, None),
            "provider_rate_limited",
            True,
        ),
        (
            urllib.error.HTTPError("https://api.openai.com", 400, "bad", {}, None),
            "analysis_failed",
            False,
        ),
    ],
)
@override_settings(OPENAI_API_KEY="test-only-key")
def test_openai_http_error_mapping_is_safe_without_network(side_effect, code, transient):
    with (
        patch("apps.analysis.providers.urllib.request.urlopen", side_effect=side_effect),
        pytest.raises(ProviderFailure) as captured,
    ):
        OpenAIAnalysisProvider().analyze(
            model="configured-model",
            system_prompt="final JSON only",
            input_payload={"task_type": "page_analysis"},
            schema={"type": "object"},
        )
    assert captured.value.code == code
    assert captured.value.transient is transient
    assert "test-only-key" not in captured.value.safe_message


@override_settings(OPENAI_API_KEY="test-only-key")
def test_openai_success_parses_only_structured_output_and_usage():
    payload = {
        "id": "response-safe-id",
        "output": [{"content": [{"type": "output_text", "text": '{"ok": true}'}]}],
        "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
    }
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(payload).encode()
    with patch("apps.analysis.providers.urllib.request.urlopen", return_value=response) as urlopen:
        result = OpenAIAnalysisProvider().analyze(
            model="configured-model",
            system_prompt="final JSON only",
            input_payload={"task_type": "page_analysis"},
            schema={"type": "object"},
        )
    assert result.structured_output == {"ok": True}
    assert result.request_id == "response-safe-id"
    assert result.usage["total_tokens"] == 3
    assert urlopen.call_args.kwargs["timeout"] == 240


@override_settings(AI_PROVIDER_CLASS="tests.test_analysis.RecordingProvider")
@patch(
    "apps.analysis.services.render_page_data_url",
    return_value=("data:image/png;base64,eA==", {}),
)
def test_succeeded_duplicate_delivery_is_noop_and_preserves_tasks(render, revision, user):
    provider = RecordingProvider()
    provider.calls = []
    with patch("apps.analysis.services.get_analysis_provider", return_value=provider):
        run = request_analysis_run(revision=revision, requested_by=user)
        assert execute_analysis_run(run.pk)["outcome"] == "succeeded"
        original = list(run.task_runs.values_list("id", "structured_result"))
        assert execute_analysis_run(run.pk) == {"outcome": "noop"}
    assert list(run.task_runs.values_list("id", "structured_result")) == original
    assert run.task_runs.filter(task_type="page_analysis").count() == 2
    assert run.task_runs.filter(task_type="document_synthesis").count() == 1


def test_valid_run_lease_prevents_second_worker_claim(revision, user):
    run = request_analysis_run(revision=revision, requested_by=user)
    first = _claim_run(run.pk)
    assert first is not None and first.status == "running"
    assert _claim_run(run.pk) is None


def test_stale_recovery_is_bounded_idempotent_and_does_not_steal_live_run(revision, user):
    run = request_analysis_run(revision=revision, requested_by=user)
    task = run.task_runs.filter(task_type="page_analysis").first()
    AnalysisRun.objects.filter(pk=run.pk).update(
        status="running", lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    AnalysisTaskRun.objects.filter(pk=task.pk).update(
        status="running", attempt_count=task.max_attempts
    )
    assert recover_stale_analysis_runs(dispatch=False) == [run.pk]
    assert recover_stale_analysis_runs(dispatch=False) == []
    with patch("apps.analysis.services.get_analysis_provider") as provider:
        assert execute_analysis_run(run.pk)["outcome"] == "failed"
        provider.return_value.analyze.assert_not_called()
    live = request_analysis_run(revision=revision, requested_by=user, predecessor=run)
    AnalysisRun.objects.filter(pk=live.pk).update(
        status="running", lease_expires_at=timezone.now() + timedelta(minutes=5)
    )
    assert recover_stale_analysis_runs(dispatch=False) == []


def test_dispatch_failure_preserves_queue_and_redispatch_is_idempotent(revision, user):
    run = request_analysis_run(revision=revision, requested_by=user)
    with patch("apps.analysis.tasks.process_analysis_run.apply_async", side_effect=OSError()):
        assert dispatch_analysis_run(run.pk) is False
    run.refresh_from_db()
    assert run.status == "queued" and run.last_dispatched_at is None
    result = SimpleNamespace(id="celery-safe-id")
    with patch("apps.analysis.tasks.process_analysis_run.apply_async", return_value=result):
        assert dispatch_analysis_run(run.pk) is True
        assert dispatch_analysis_run(run.pk) is False


@override_settings(AI_MAX_PAGES_PER_RUN=1)
def test_page_limit_rejects_without_status_change(revision, user):
    with pytest.raises(ValidationError):
        request_analysis_run(revision=revision, requested_by=user)
    assert Project.objects.get(pk=revision.document.project_id).status == "documents_uploaded"


@override_settings(AI_MAX_NATIVE_TEXT_CHARS=5)
def test_native_text_truncation_is_explicit_in_task_metadata_and_payload(revision, user):
    run = request_analysis_run(revision=revision, requested_by=user)
    task = run.task_runs.get(document_page__page_number=1)
    assert task.input_metadata["native_text_truncated"] is True
    from apps.analysis.services import _page_payload

    payload = _page_payload(task)
    assert payload["page"]["native_text"] == "Bid c"
    assert payload["page"]["native_text_truncated"] is True


def completed_run(revision, user):
    provider = RecordingProvider()
    provider.calls = []
    with (
        patch("apps.analysis.services.get_analysis_provider", return_value=provider),
        patch(
            "apps.analysis.services.render_page_data_url",
            return_value=("data:image/png;base64,eA==", {}),
        ),
    ):
        run = request_analysis_run(revision=revision, requested_by=user)
        assert execute_analysis_run(run.pk)["outcome"] == "succeeded"
    run.refresh_from_db()
    return run


def test_successful_run_materializes_idempotent_findings_and_sources(revision, user, membership):
    run = completed_run(revision, user)
    with patch("apps.analysis.services.get_analysis_provider") as provider:
        first = list(materialize_findings(analysis_run=run, actor=user))
        second = list(materialize_findings(analysis_run=run, actor=user))
        provider.assert_not_called()
    assert len(first) == len(second) == 2
    assert ExtractedFinding.objects.filter(analysis_run=run).count() == 2
    assert FindingSource.objects.filter(finding__analysis_run=run).count() == 2
    assert {source.document_page_id for source in FindingSource.objects.all()} == set(
        revision.pages.values_list("id", flat=True)
    )
    assert Project.objects.get(pk=revision.document.project_id).status == "human_scope_review"
    assert AuditEvent.objects.filter(action_code="findings.materialized").count() == 1


@pytest.mark.parametrize(
    ("excerpt", "page_text", "expected"),
    [
        ("Exact source text", "Before Exact source text After", ("Exact source text", "exact")),
        (
            "Supply   and\ninstall work",
            "Before Supply and\r\ninstall work After",
            ("Supply and\r\ninstall work", "whitespace"),
        ),
        ("Area 6476 sqm", "Area details from schedule 6476 sqm", None),
        ("Supply ... work", "Supply and install work", None),
        ("work Supply", "Supply work", None),
        ("Provide equipment", "Supply equipment", None),
        ("A  B", "A\nB then A\tB", None),
    ],
)
def test_grounded_excerpt_requires_unique_contiguous_source(excerpt, page_text, expected):
    assert _grounded_excerpt(excerpt, page_text) == expected


def test_materialization_recovers_grounded_sources_and_skips_invalid_candidates(
    revision, user, membership
):
    run = completed_run(revision, user)
    page_tasks = list(
        run.task_runs.filter(task_type="page_analysis")
        .select_related("document_page")
        .order_by("id")
    )
    payload = deepcopy(run.result_summary)
    valid = payload["candidates"][0]
    valid_evidence = valid["evidence"][0]
    valid_evidence["evidence_excerpt"] = "Bid   closes\nSeptember 15."
    invalid_evidence = deepcopy(valid_evidence)
    invalid_evidence["evidence_excerpt"] = "Bid ... September 15."
    valid["evidence"].append(invalid_evidence)
    invalid = payload["candidates"][1]
    invalid["evidence"][0]["evidence_excerpt"] = "M01 ... PLAN"
    synthesis = run.task_runs.get(task_type="document_synthesis")
    AnalysisRun.objects.filter(pk=run.pk).update(result_summary=payload)
    AnalysisTaskRun.objects.filter(pk=synthesis.pk).update(structured_result=payload)
    run.refresh_from_db()
    original_provider_output = deepcopy(run.result_summary)
    original_page_text = list(revision.pages.order_by("id").values_list("id", "native_text"))

    first = list(materialize_findings(analysis_run=run, actor=user))
    second = list(materialize_findings(analysis_run=run, actor=user))

    assert [finding.pk for finding in first] == [finding.pk for finding in second]
    assert len(first) == 1
    sources = list(first[0].sources.all())
    assert len(sources) == 1
    assert sources[0].evidence_excerpt == "Bid closes September 15."
    assert sources[0].document_page_id == page_tasks[0].document_page_id
    event = AuditEvent.objects.get(action_code="findings.materialized", target_id=str(run.pk))
    assert event.metadata == {
        "finding_count": 1,
        "candidates_considered": 2,
        "candidates_materialized": 1,
        "candidates_skipped_no_valid_provenance": 1,
        "evidence_refs_accepted_exact": 0,
        "evidence_refs_recovered_whitespace": 1,
        "evidence_refs_rejected_invalid": 2,
    }
    assert (
        AuditEvent.objects.filter(
            action_code="findings.materialized", target_id=str(run.pk)
        ).count()
        == 1
    )
    run.refresh_from_db()
    assert run.result_summary == original_provider_output
    assert list(revision.pages.order_by("id").values_list("id", "native_text")) == (
        original_page_text
    )

    sources[0].evidence_excerpt = "Paraphrased evidence"
    with pytest.raises(ValidationError, match="Excerpt must occur"):
        sources[0].full_clean()


@pytest.mark.parametrize("status", ["queued", "running", "failed"])
def test_only_successful_run_can_materialize_without_status_change(status, revision, user):
    run = request_analysis_run(revision=revision, requested_by=user)
    AnalysisRun.objects.filter(pk=run.pk).update(status=status)
    run.refresh_from_db()
    with pytest.raises(ValidationError):
        materialize_findings(analysis_run=run, actor=user)
    assert not ExtractedFinding.objects.exists()
    assert Project.objects.get(pk=revision.document.project_id).status == "ai_analysis"


def test_reviews_are_append_only_and_preserve_machine_value(revision, user, membership):
    run = completed_run(revision, user)
    finding = materialize_findings(analysis_run=run, actor=user).first()
    machine_value = finding.machine_value
    accepted, accepted_created = review_finding(
        finding=finding, reviewer=user, decision=FindingReview.Decision.ACCEPTED
    )
    edited, edited_created = review_finding(
        finding=finding,
        reviewer=user,
        decision=FindingReview.Decision.EDITED_ACCEPTED,
        reviewed_value="Human corrected value",
        review_note="Verified against addendum.",
    )
    rejected, rejected_created = review_finding(
        finding=finding, reviewer=user, decision=FindingReview.Decision.REJECTED
    )
    finding.refresh_from_db()
    assert accepted_created and edited_created and rejected_created
    assert [accepted.pk, edited.pk, rejected.pk] == list(
        finding.reviews.values_list("pk", flat=True)
    )
    assert edited.supersedes == accepted and rejected.supersedes == edited
    assert finding.machine_value == machine_value
    assert finding.review_status == "rejected"
    assert finding.effective_value == ""


@pytest.mark.parametrize(
    ("decision", "action_code"),
    [
        (FindingReview.Decision.NEEDS_CLARIFICATION, "finding.needs_clarification"),
        (FindingReview.Decision.ACCEPTED, "finding.accepted"),
        (FindingReview.Decision.REJECTED, "finding.rejected"),
    ],
)
def test_identical_consecutive_review_is_idempotent(
    decision, action_code, revision, user, membership
):
    run = completed_run(revision, user)
    finding = materialize_findings(analysis_run=run, actor=user).first()
    machine_value = finding.machine_value
    first, first_created = review_finding(
        finding=finding,
        reviewer=user,
        decision=decision,
        reviewed_value=None,
        review_note="  ",
    )
    second, second_created = review_finding(
        finding=finding,
        reviewer=user,
        decision=decision,
        reviewed_value="",
        review_note="",
    )
    finding.refresh_from_db()
    assert first_created is True and second_created is False
    assert second.pk == first.pk
    assert FindingReview.objects.filter(finding=finding).count() == 1
    assert AuditEvent.objects.filter(action_code=action_code, target_id=str(first.pk)).count() == 1
    assert finding.machine_value == machine_value


def test_meaningful_review_changes_append_without_changing_machine_value(
    revision, user, membership
):
    run = completed_run(revision, user)
    finding = materialize_findings(analysis_run=run, actor=user).first()
    machine_value = finding.machine_value
    clarification, _ = review_finding(
        finding=finding,
        reviewer=user,
        decision=FindingReview.Decision.NEEDS_CLARIFICATION,
        review_note="Need architect confirmation",
    )
    changed_note, changed_note_created = review_finding(
        finding=finding,
        reviewer=user,
        decision=FindingReview.Decision.NEEDS_CLARIFICATION,
        review_note=" Architect response received but still ambiguous ",
    )
    edited, _ = review_finding(
        finding=finding,
        reviewer=user,
        decision=FindingReview.Decision.EDITED_ACCEPTED,
        reviewed_value="First reviewed value",
    )
    changed_value, changed_value_created = review_finding(
        finding=finding,
        reviewer=user,
        decision=FindingReview.Decision.EDITED_ACCEPTED,
        reviewed_value=" Second reviewed value ",
    )
    rejected, rejected_created = review_finding(
        finding=finding,
        reviewer=user,
        decision=FindingReview.Decision.REJECTED,
    )
    accepted, accepted_created = review_finding(
        finding=finding,
        reviewer=user,
        decision=FindingReview.Decision.ACCEPTED,
    )
    finding.refresh_from_db()
    assert changed_note_created and changed_value_created and rejected_created and accepted_created
    assert changed_note.supersedes == clarification
    assert changed_note.review_note == "Architect response received but still ambiguous"
    assert changed_value.supersedes == edited
    assert changed_value.reviewed_value == "Second reviewed value"
    assert rejected.supersedes == changed_value and accepted.supersedes == rejected
    assert finding.reviews.count() == 6
    assert finding.machine_value == machine_value


def test_repeated_identical_review_api_post_returns_existing_review(
    revision, user, membership, organization
):
    run = completed_run(revision, user)
    finding = materialize_findings(analysis_run=run, actor=user).first()
    url = reverse(
        "finding-review-list",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": revision.document.project_id,
            "finding_pk": finding.pk,
        },
    )
    payload = {"decision": "needs_clarification", "review_note": "  Confirm with architect  "}
    first = client_for(user).post(url, payload, format="json")
    second = client_for(user).post(url, payload, format="json")
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert second.data["review_note"] == "Confirm with architect"
    assert FindingReview.objects.filter(finding=finding).count() == 1
    assert AuditEvent.objects.filter(action_code="finding.needs_clarification").count() == 1


def test_finding_and_source_ownership_and_immutability(revision, user, membership):
    run = completed_run(revision, user)
    finding = materialize_findings(analysis_run=run, actor=user).first()
    source = finding.sources.first()
    finding.machine_value = "changed"
    with pytest.raises(ValidationError):
        finding.save()
    source.evidence_excerpt = "changed"
    with pytest.raises(ValidationError):
        source.save()
    other_page = revision.pages.exclude(pk=source.document_page_id).first()
    source.document_page = other_page
    with pytest.raises(ValidationError):
        source.full_clean()


def test_conflict_detection_is_conservative_and_idempotent(revision, user, membership):
    run = completed_run(revision, user)
    findings = list(materialize_findings(analysis_run=run, actor=user))
    assert detect_conflicts(analysis_run=run, actor=user) == []
    original = findings[0]
    conflicting = ExtractedFinding(
        analysis_run=run,
        analysis_task_run=original.analysis_task_run,
        document_revision=revision,
        source_candidate_key="different-value-key",
        semantic_key=original.semantic_key,
        category=original.category,
        subject=original.subject,
        machine_value="Different mechanical responsibility",
        normalized_machine_value="different mechanical responsibility",
        machine_support="explicit",
        schema_version=run.schema_version,
    )
    conflicting.full_clean()
    conflicting.save()
    # Scope/trade values are intentionally excluded from automatic conflict claims.
    assert detect_conflicts(analysis_run=run, actor=user) == []
    original.category = "responsibility"
    original.semantic_key = "responsibility.fixture_supply"
    original.source_candidate_key = "responsibility-a"
    original.pk = None
    original._state.adding = True
    original.save(force_insert=True)
    second = ExtractedFinding.objects.create(
        analysis_run=run,
        analysis_task_run=original.analysis_task_run,
        document_revision=revision,
        source_candidate_key="responsibility-b",
        semantic_key="responsibility.fixture_supply",
        category="responsibility",
        subject="Fixture supply",
        machine_value="Owner",
        normalized_machine_value="owner",
        machine_support="explicit",
        schema_version=run.schema_version,
    )
    original.normalized_machine_value = "general contractor"
    ExtractedFinding.objects.filter(pk=original.pk).update(
        normalized_machine_value="general contractor", machine_value="General contractor"
    )
    created = detect_conflicts(analysis_run=run, actor=user)
    assert len(created) == 1
    assert set(created[0].findings.values_list("pk", flat=True)) == {original.pk, second.pk}
    assert detect_conflicts(analysis_run=run, actor=user) == []


def test_conflict_resolution_is_append_only_and_audited(revision, user, membership):
    run = completed_run(revision, user)
    task = run.task_runs.get(task_type="document_synthesis")
    common = dict(
        analysis_run=run,
        analysis_task_run=task,
        document_revision=revision,
        semantic_key="date_deadline.tender_close",
        category="date_deadline",
        subject="Tender close",
        machine_support="explicit",
        schema_version=run.schema_version,
    )
    for key, value in (("date-a", "2026-09-15"), ("date-b", "2026-09-16")):
        ExtractedFinding.objects.create(
            **common,
            source_candidate_key=key,
            machine_value=value,
            normalized_machine_value=value,
        )
    conflict = detect_conflicts(analysis_run=run, actor=user)[0]
    resolved = resolve_conflict(
        conflict=conflict,
        actor=user,
        status=IntelligenceConflict.Status.RESOLVED,
        resolution_note="Addendum controls.",
    )
    assert conflict.status == "open"
    assert resolved.supersedes == conflict and resolved.version == 2
    assert resolved.status == "resolved"
    assert AuditEvent.objects.filter(action_code="conflict.resolved").exists()


def test_multiple_analysis_runs_keep_findings_and_reviews_isolated(revision, user, membership):
    first = completed_run(revision, user)
    first_finding = materialize_findings(analysis_run=first, actor=user).first()
    review_finding(finding=first_finding, reviewer=user, decision=FindingReview.Decision.ACCEPTED)
    second = completed_run(revision, user)
    materialize_findings(analysis_run=second, actor=user)
    first_finding.refresh_from_db()
    assert first.findings.count() == second.findings.count() == 2
    assert first_finding.reviews.count() == 1
    assert not FindingReview.objects.filter(finding__analysis_run=second).exists()


def test_review_api_permissions_scoping_and_read_only_boundaries(
    revision, user, membership, organization
):
    run = completed_run(revision, user)
    materialize_url = reverse(
        "analysis-run-findings-materialize",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": revision.document.project_id,
            "run_pk": run.pk,
        },
    )
    viewer = get_user_model().objects.create_user(email="review-viewer@example.com", password="x")
    Membership.objects.create(organization=organization, user=viewer, role=Membership.Role.VIEWER)
    assert client_for(viewer).post(materialize_url, {}, format="json").status_code == 403
    response = client_for(user).post(materialize_url, {}, format="json")
    assert response.status_code == 200
    finding = ExtractedFinding.objects.filter(analysis_run=run).first()
    detail_url = reverse(
        "finding-detail",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": revision.document.project_id,
            "finding_pk": finding.pk,
        },
    )
    review_url = reverse(
        "finding-review-list",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": revision.document.project_id,
            "finding_pk": finding.pk,
        },
    )
    assert client_for(viewer).get(detail_url).status_code == 200
    assert client_for(viewer).post(review_url, {"decision": "accepted"}).status_code == 403
    assert (
        client_for(user)
        .post(
            review_url,
            {"decision": "edited_accepted", "reviewed_value": "Reviewed text"},
            format="json",
        )
        .status_code
        == 201
    )
    assert client_for(user).delete(detail_url).status_code == 405
    payload = client_for(user).get(detail_url).data
    serialized = json.dumps(payload)
    assert "storage_key" not in serialized and '"native_text":' not in serialized
    assert "OPENAI_API_KEY" not in serialized and "normalized_machine_value" not in payload


def snapshot_ready_run(revision, user):
    Document.objects.filter(pk=revision.document_id).update(current_revision=revision)
    Project.objects.filter(pk=revision.document.project_id).update(
        status=Project.Status.HUMAN_SCOPE_REVIEW
    )
    revision.document.project.refresh_from_db()
    run = completed_run(revision, user)
    findings = list(materialize_findings(analysis_run=run, actor=user))
    for finding in findings:
        review_finding(finding=finding, reviewer=user, decision=FindingReview.Decision.ACCEPTED)
    run.refresh_from_db()
    return run, findings


def second_document_revision(revision, user):
    project = revision.document.project
    original = revision.project_file.file_asset
    asset = FileAsset.objects.create(
        organization=project.organization,
        bucket=original.bucket,
        storage_key="analysis/second-source.pdf",
        original_filename="second-source.pdf",
        declared_mime_type="application/pdf",
        detected_mime_type="application/pdf",
        byte_size=original.byte_size,
        checksum=original.checksum,
        created_by=user,
    )
    project_file = ProjectFile.objects.create(project=project, file_asset=asset, created_by=user)
    document = Document.objects.create(
        project=project,
        title="Second Drawing Set",
        category=Document.Category.DRAWINGS,
        created_by=user,
    )
    other = DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        revision_label="R1",
        source_filename="second-source.pdf",
        created_by=user,
    )
    page = DocumentPage.objects.create(
        document_revision=other,
        page_number=1,
        page_label="A01",
        width_points=612,
        height_points=792,
        native_text="A01 ARCHITECTURAL PLAN",
        native_text_char_count=22,
        has_native_text=True,
        parser_name="PyMuPDF",
        parser_version="1.28.2",
    )
    for job_type in (ProcessingJob.JobType.SOURCE_VERIFICATION, ProcessingJob.JobType.PDF_INDEXING):
        ProcessingJob.objects.create(
            document_revision=other,
            job_type=job_type,
            status=ProcessingJob.Status.SUCCEEDED,
            requested_by=user,
            finished_at=page.indexed_at,
        )
    Document.objects.filter(pk=document.pk).update(current_revision=other)
    return other


def test_snapshot_readiness_blocks_incomplete_reviews_and_open_conflicts(
    revision, user, membership
):
    Document.objects.filter(pk=revision.document_id).update(current_revision=revision)
    run = completed_run(revision, user)
    findings = list(materialize_findings(analysis_run=run, actor=user))
    revision.document.project.refresh_from_db()
    state = snapshot_readiness(project=revision.document.project, run_ids=[run.pk])
    assert state["eligible"] is False
    assert {item["code"] for item in state["blockers"]} == {"unreviewed"}
    review_finding(
        finding=findings[0],
        reviewer=user,
        decision=FindingReview.Decision.NEEDS_CLARIFICATION,
    )
    review_finding(finding=findings[1], reviewer=user, decision=FindingReview.Decision.REJECTED)
    state = snapshot_readiness(project=revision.document.project, run_ids=[run.pk])
    assert state["eligible"] is False
    assert state["summary_counts"]["needs_clarification"] == 1
    assert state["summary_counts"]["rejected"] == 1


def test_snapshot_freezes_complete_review_and_provenance_manifest_idempotently(
    revision, user, membership
):
    run, findings = snapshot_ready_run(revision, user)
    machine_value = findings[0].machine_value
    review_finding(
        finding=findings[0],
        reviewer=user,
        decision=FindingReview.Decision.EDITED_ACCEPTED,
        reviewed_value="Human reviewed value",
    )
    review_finding(finding=findings[1], reviewer=user, decision=FindingReview.Decision.REJECTED)
    with patch("apps.analysis.services.get_analysis_provider") as provider:
        snapshot, created = create_intelligence_snapshot(
            project=revision.document.project, creator=user, run_ids=[run.pk]
        )
        repeated, repeated_created = create_intelligence_snapshot(
            project=revision.document.project, creator=user, run_ids=[run.pk]
        )
        provider.assert_not_called()
    assert created is True and repeated_created is False and repeated.pk == snapshot.pk
    assert snapshot.entries.count() == len(findings)
    assert snapshot.entries.filter(included_in_intelligence=True).count() == 1
    assert snapshot.entries.get(finding=findings[0]).effective_value == "Human reviewed value"
    assert snapshot.entries.get(finding=findings[1]).effective_value == ""
    assert (
        ProjectIntelligenceSnapshotProvenance.objects.filter(
            snapshot_entry__snapshot=snapshot
        ).count()
        == FindingSource.objects.filter(finding__analysis_run=run).count()
    )
    assert snapshot.manifest["source_runs"][0]["analysis_run_id"] == run.pk
    assert {item["finding_id"] for item in snapshot.manifest["source_runs"][0]["findings"]} == {
        finding.pk for finding in findings
    }
    findings[0].refresh_from_db()
    assert findings[0].machine_value == machine_value
    snapshot.version = 99
    with pytest.raises(ValidationError):
        snapshot.save()


def test_snapshot_multi_run_selection_and_same_revision_guard(revision, user, membership):
    first_run, first_findings = snapshot_ready_run(revision, user)
    other_revision = second_document_revision(revision, user)
    second_run, second_findings = snapshot_ready_run(other_revision, user)
    snapshot, created = create_intelligence_snapshot(
        project=revision.document.project, creator=user, run_ids=[second_run.pk, first_run.pk]
    )
    assert created and snapshot.sources.count() == 2
    assert snapshot.entries.count() == len(first_findings) + len(second_findings)
    another_run = completed_run(revision, user)
    for finding in materialize_findings(analysis_run=another_run, actor=user):
        review_finding(finding=finding, reviewer=user, decision=FindingReview.Decision.ACCEPTED)
    state = snapshot_readiness(
        project=revision.document.project, run_ids=[first_run.pk, another_run.pk]
    )
    assert state["eligible"] is False
    assert "duplicate_revision_run" in {item["code"] for item in state["blockers"]}


def test_historical_revision_cannot_create_new_snapshot(revision, user, membership):
    run, _ = snapshot_ready_run(revision, user)
    replacement = second_document_revision(revision, user)
    Document.objects.filter(pk=revision.document_id).update(current_revision=None)
    state = snapshot_readiness(project=revision.document.project, run_ids=[run.pk])
    assert state["eligible"] is False
    assert "revision_not_current" in {item["code"] for item in state["blockers"]}
    assert replacement.document_id != revision.document_id


def test_archived_document_is_excluded_from_new_snapshot_and_restore_recovers_readiness(
    revision, user, membership, organization
):
    run, _ = snapshot_ready_run(revision, user)
    document = revision.document
    set_document_active(document=document, is_active=False, actor=user)
    state = snapshot_readiness(project=document.project, run_ids=[run.pk])
    assert state["eligible"] is False
    assert "document_archived" in {item["code"] for item in state["blockers"]}
    endpoint = reverse(
        "intelligence-readiness",
        kwargs={"organization_slug": organization.slug, "project_pk": document.project_id},
    )
    assert client_for(user).get(endpoint).data["candidate_runs"] == []
    set_document_active(document=document, is_active=True, actor=user)
    assert snapshot_readiness(project=document.project, run_ids=[run.pk])["eligible"] is True


def test_archive_blocks_draft_approval_without_creating_staleness(
    revision, user, membership, organization
):
    run, _ = snapshot_ready_run(revision, user)
    snapshot, _ = create_intelligence_snapshot(
        project=revision.document.project, creator=user, run_ids=[run.pk]
    )
    fingerprint = snapshot.fingerprint
    manifest = snapshot.manifest
    set_document_active(document=revision.document, is_active=False, actor=user)

    fresh = snapshot_freshness(project=revision.document.project, run_ids=[run.pk])
    assert fresh["eligible"] is True and fresh["fingerprint"] == fingerprint
    with pytest.raises(ValidationError, match="document_archived"):
        approve_intelligence_snapshot(snapshot=snapshot, approver=user)
    snapshot.refresh_from_db()
    assert snapshot.fingerprint == fingerprint and snapshot.manifest == manifest
    assert not ProjectIntelligenceApproval.objects.filter(snapshot=snapshot).exists()

    detail = reverse(
        "intelligence-snapshot-detail",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": revision.document.project_id,
            "snapshot_pk": snapshot.pk,
        },
    )
    payload = client_for(user).get(detail).data
    assert payload["is_stale"] is False
    assert payload["approval_blockers"][0]["code"] == "document_archived"
    assert payload["sources"][0]["document_is_active"] is False

    set_document_active(document=revision.document, is_active=True, actor=user)
    approval, created = approve_intelligence_snapshot(snapshot=snapshot, approver=user)
    assert created is True and approval.snapshot_id == snapshot.pk


def test_approved_snapshot_remains_approved_and_fresh_when_source_is_archived(
    revision, user, membership, organization
):
    run, _ = snapshot_ready_run(revision, user)
    snapshot, _ = create_intelligence_snapshot(
        project=revision.document.project, creator=user, run_ids=[run.pk]
    )
    approval, _ = approve_intelligence_snapshot(snapshot=snapshot, approver=user)
    fingerprint, manifest = snapshot.fingerprint, snapshot.manifest
    set_document_active(document=revision.document, is_active=False, actor=user)
    detail = reverse(
        "intelligence-snapshot-detail",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": revision.document.project_id,
            "snapshot_pk": snapshot.pk,
        },
    )
    payload = client_for(user).get(detail).data
    snapshot.refresh_from_db()
    approval.refresh_from_db()
    assert payload["is_stale"] is False
    assert payload["approval"]["id"] == approval.pk
    assert payload["sources"][0]["document_is_active"] is False
    assert snapshot.fingerprint == fingerprint and snapshot.manifest == manifest


def test_snapshot_approval_self_approval_idempotency_and_staleness(revision, user, membership):
    run, findings = snapshot_ready_run(revision, user)
    snapshot, _ = create_intelligence_snapshot(
        project=revision.document.project, creator=user, run_ids=[run.pk]
    )
    approval, created = approve_intelligence_snapshot(
        snapshot=snapshot, approver=user, approval_note="Approved for M1 intelligence."
    )
    repeated, repeated_created = approve_intelligence_snapshot(snapshot=snapshot, approver=user)
    assert created and not repeated_created and repeated.pk == approval.pk
    assert ProjectIntelligenceApproval.objects.filter(snapshot=snapshot).count() == 1
    assert AuditEvent.objects.filter(action_code="intelligence_snapshot.approved").count() == 1
    assert (
        Project.objects.get(pk=revision.document.project_id).status
        == Project.Status.HUMAN_SCOPE_REVIEW
    )
    frozen = snapshot.manifest
    review_finding(finding=findings[0], reviewer=user, decision=FindingReview.Decision.REJECTED)
    snapshot.refresh_from_db()
    approval.refresh_from_db()
    assert snapshot.manifest == frozen and approval.snapshot_id == snapshot.pk


def test_stale_unapproved_snapshot_is_blocked_and_new_version_created(revision, user, membership):
    run, findings = snapshot_ready_run(revision, user)
    first, _ = create_intelligence_snapshot(
        project=revision.document.project, creator=user, run_ids=[run.pk]
    )
    review_finding(finding=findings[0], reviewer=user, decision=FindingReview.Decision.REJECTED)
    with pytest.raises(ValidationError, match="snapshot_stale"):
        approve_intelligence_snapshot(snapshot=first, approver=user)
    assert not ProjectIntelligenceApproval.objects.filter(snapshot=first).exists()
    assert AuditEvent.objects.filter(
        action_code="intelligence_snapshot.approval_blocked_stale"
    ).exists()
    second, created = create_intelligence_snapshot(
        project=revision.document.project, creator=user, run_ids=[run.pk]
    )
    assert created and second.version == 2 and second.fingerprint != first.fingerprint


def test_snapshot_api_operator_viewer_and_no_cherry_pick(revision, user, membership, organization):
    run, findings = snapshot_ready_run(revision, user)
    list_endpoint = reverse(
        "intelligence-snapshot-list",
        kwargs={"organization_slug": organization.slug, "project_pk": revision.document.project_id},
    )
    response = client_for(user).post(
        list_endpoint,
        {"analysis_run_ids": [run.pk], "finding_ids": [findings[0].pk]},
        format="json",
    )
    assert response.status_code == 201
    assert sum(len(source["entries"]) for source in response.data["sources"]) == len(findings)
    approval_endpoint = reverse(
        "intelligence-snapshot-approval",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": revision.document.project_id,
            "snapshot_pk": response.data["id"],
        },
    )
    assert (
        client_for(user)
        .post(approval_endpoint, {"approval_note": "Self-approved"}, format="json")
        .status_code
        == 201
    )
    viewer = get_user_model().objects.create_user(email="snapshot-viewer@example.com", password="x")
    Membership.objects.create(organization=organization, user=viewer, role=Membership.Role.VIEWER)
    viewer_client = client_for(viewer)
    assert viewer_client.get(list_endpoint).status_code == 200
    assert (
        viewer_client.post(list_endpoint, {"analysis_run_ids": [run.pk]}, format="json").status_code
        == 403
    )
    assert viewer_client.post(approval_endpoint, {}, format="json").status_code == 403
    assert viewer_client.put(list_endpoint, {}, format="json").status_code == 405
    assert viewer_client.delete(list_endpoint).status_code == 405
    serialized = json.dumps(viewer_client.get(list_endpoint).data)
    assert "native_text" not in serialized and "storage_key" not in serialized
    assert "OPENAI_API_KEY" not in serialized


def test_snapshot_readiness_blocks_open_conflict_and_missing_provenance(revision, user, membership):
    run, findings = snapshot_ready_run(revision, user)
    conflict = IntelligenceConflict.objects.create(
        project=revision.document.project,
        analysis_run=run,
        semantic_key=findings[0].semantic_key,
        participant_key="snapshot-open-conflict",
        explanation="Conflicting reviewed evidence requires a human resolution.",
    )
    conflict.findings.add(findings[0])
    state = snapshot_readiness(project=revision.document.project, run_ids=[run.pk])
    assert "open_conflict" in {item["code"] for item in state["blockers"]}

    conflict.delete()
    findings[0].sources.all().delete()
    state = snapshot_readiness(project=revision.document.project, run_ids=[run.pk])
    assert "missing_provenance" in {item["code"] for item in state["blockers"]}


def test_snapshot_api_admin_allowed_and_inactive_membership_denied(
    revision, user, membership, organization
):
    run, _ = snapshot_ready_run(revision, user)
    endpoint = reverse(
        "intelligence-snapshot-list",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": revision.document.project_id,
        },
    )
    admin = get_user_model().objects.create_user(email="snapshot-admin@example.com", password="x")
    Membership.objects.create(organization=organization, user=admin, role=Membership.Role.ADMIN)
    response = client_for(admin).post(endpoint, {"analysis_run_ids": [run.pk]}, format="json")
    assert response.status_code == 201
    approval_endpoint = reverse(
        "intelligence-snapshot-approval",
        kwargs={
            "organization_slug": organization.slug,
            "project_pk": revision.document.project_id,
            "snapshot_pk": response.data["id"],
        },
    )
    assert client_for(admin).post(approval_endpoint, {}, format="json").status_code == 201

    admin.memberships.update(is_active=False)
    assert client_for(admin).get(endpoint).status_code == 403
