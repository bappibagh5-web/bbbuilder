import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.documents.storage import ObjectStorageError, get_object_storage
from apps.projects.audit import record_event

from .models import ProcessingJob

logger = logging.getLogger(__name__)


class SourceVerificationFailure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.safe_message = message


def _log(event, job, **extra):
    logger.info(
        event,
        extra={
            "processing_job_id": job.pk,
            "revision_id": job.document_revision_id,
            "project_id": job.project.pk,
            "organization_id": job.organization.pk,
            **extra,
        },
    )


def dispatch_processing_job(job_id, *, force=False):
    from .tasks import process_processing_job

    job = ProcessingJob.objects.get(pk=job_id)
    if job.status != ProcessingJob.Status.QUEUED:
        return False
    redispatch_after = timezone.now() - timedelta(
        seconds=settings.PROCESSING_REDISPATCH_INTERVAL_SECONDS
    )
    if not force and job.last_dispatched_at and job.last_dispatched_at > redispatch_after:
        return False
    try:
        result = process_processing_job.apply_async(args=(job.pk,))
    except Exception:
        logger.exception(
            "Processing job dispatch failed; durable job remains queued.",
            extra={"processing_job_id": job.pk},
        )
        return False
    ProcessingJob.objects.filter(pk=job.pk, status=ProcessingJob.Status.QUEUED).update(
        celery_task_id=result.id,
        last_dispatched_at=timezone.now(),
        dispatch_attempt_count=F("dispatch_attempt_count") + 1,
    )
    _log("Processing job dispatched.", job)
    return True


def dispatch_processing_job_safely(job_id):
    dispatch_processing_job(job_id)


def request_source_verification(
    *, revision, requested_by, audit_action="processing.requested", dispatch=True
):
    try:
        with transaction.atomic():
            job = ProcessingJob.objects.create(
                document_revision=revision,
                requested_by=requested_by,
            )
            record_event(
                organization=revision.document.project.organization,
                project=revision.document.project,
                actor=requested_by,
                action_code=audit_action,
                target=job,
                metadata={
                    "document_id": revision.document_id,
                    "document_revision_id": revision.pk,
                    "job_type": job.job_type,
                },
            )
            if dispatch and settings.PROCESSING_AUTO_DISPATCH:
                transaction.on_commit(lambda: dispatch_processing_job_safely(job.pk))
    except IntegrityError as error:
        raise ValidationError(
            "This revision already has queued or running source verification."
        ) from error
    return job


def retry_processing_job(*, job, requested_by):
    if job.status != ProcessingJob.Status.FAILED:
        raise ValidationError("Only a failed processing job can be retried.")
    return request_source_verification(
        revision=job.document_revision,
        requested_by=requested_by,
        audit_action="processing.retry_requested",
    )


def claim_processing_job(job_id):
    now = timezone.now()
    with transaction.atomic():
        job = (
            ProcessingJob.objects.select_for_update()
            .select_related(
                "document_revision__document__project__organization",
                "document_revision__project_file__file_asset",
            )
            .get(pk=job_id)
        )
        if job.status in {ProcessingJob.Status.SUCCEEDED, ProcessingJob.Status.FAILED}:
            return None
        if (
            job.status == ProcessingJob.Status.RUNNING
            and job.lease_expires_at
            and job.lease_expires_at > now
        ):
            return None
        job.status = ProcessingJob.Status.RUNNING
        job.attempt_count += 1
        job.started_at = now
        job.finished_at = None
        job.heartbeat_at = now
        job.lease_expires_at = job.lease_until(now)
        job.error_code = ""
        job.error_message = ""
        job.result_metadata = {}
        job.save(
            update_fields=(
                "status",
                "attempt_count",
                "started_at",
                "finished_at",
                "heartbeat_at",
                "lease_expires_at",
                "error_code",
                "error_message",
                "result_metadata",
                "updated_at",
            )
        )
    _log("Processing job claimed.", job, status=job.status)
    return job


def heartbeat(job_id):
    now = timezone.now()
    ProcessingJob.objects.filter(pk=job_id, status=ProcessingJob.Status.RUNNING).update(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=settings.PROCESSING_JOB_LEASE_SECONDS),
    )


def verify_source(job):
    asset = job.document_revision.project_file.file_asset
    if asset.checksum_algorithm != asset.ChecksumAlgorithm.SHA256:
        raise SourceVerificationFailure(
            ProcessingJob.ErrorCode.PROCESSING_ERROR,
            "This checksum algorithm is not supported for source verification.",
        )
    stored_file = get_object_storage().open(asset.storage_key)
    if stored_file is None:
        raise SourceVerificationFailure(
            ProcessingJob.ErrorCode.SOURCE_MISSING,
            "The stored source file could not be found.",
        )
    digest = hashlib.sha256()
    byte_count = 0
    next_heartbeat = settings.PROCESSING_HEARTBEAT_BYTES
    try:
        while True:
            chunk = stored_file.read(settings.PROCESSING_STREAM_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            byte_count += len(chunk)
            if byte_count >= next_heartbeat:
                heartbeat(job.pk)
                next_heartbeat += settings.PROCESSING_HEARTBEAT_BYTES
    finally:
        stored_file.close()
    if byte_count != asset.byte_size:
        raise SourceVerificationFailure(
            ProcessingJob.ErrorCode.SIZE_MISMATCH,
            "The stored source file size does not match its immutable metadata.",
        )
    checksum = digest.hexdigest()
    if checksum != asset.checksum:
        raise SourceVerificationFailure(
            ProcessingJob.ErrorCode.CHECKSUM_MISMATCH,
            "The stored source file checksum does not match its immutable metadata.",
        )
    return {
        "verified_byte_size": byte_count,
        "verified_checksum_algorithm": "sha256",
        "checksum_match": True,
        "verified_at": timezone.now().isoformat(),
    }


def finish_job(job_id, *, status, error_code="", error_message="", result_metadata=None):
    now = timezone.now()
    ProcessingJob.objects.filter(pk=job_id, status=ProcessingJob.Status.RUNNING).update(
        status=status,
        finished_at=now,
        heartbeat_at=now,
        lease_expires_at=None,
        error_code=error_code,
        error_message=error_message,
        result_metadata=result_metadata or {},
    )


def requeue_transient_failure(job, *, code, message):
    ProcessingJob.objects.filter(pk=job.pk, status=ProcessingJob.Status.RUNNING).update(
        status=ProcessingJob.Status.QUEUED,
        queued_at=timezone.now(),
        started_at=None,
        heartbeat_at=None,
        lease_expires_at=None,
        error_code=code,
        error_message=message,
        result_metadata={},
    )


def execute_processing_job(job_id):
    job = claim_processing_job(job_id)
    if job is None:
        return {"outcome": "noop"}
    try:
        result = verify_source(job)
    except SourceVerificationFailure as error:
        finish_job(
            job.pk,
            status=ProcessingJob.Status.FAILED,
            error_code=error.code,
            error_message=error.safe_message,
        )
        _log("Processing job failed.", job, error_code=error.code)
        return {"outcome": "failed", "error_code": error.code}
    except ObjectStorageError:
        message = "Object storage is temporarily unavailable."
        if job.attempt_count < job.max_attempts:
            requeue_transient_failure(
                job,
                code=ProcessingJob.ErrorCode.STORAGE_UNAVAILABLE,
                message=message,
            )
            countdown = settings.PROCESSING_RETRY_BASE_SECONDS * (2 ** (job.attempt_count - 1))
            _log("Processing job queued for retry.", job, error_code="storage_unavailable")
            return {"outcome": "retry", "countdown": countdown}
        finish_job(
            job.pk,
            status=ProcessingJob.Status.FAILED,
            error_code=ProcessingJob.ErrorCode.STORAGE_UNAVAILABLE,
            error_message=message,
        )
        _log("Processing job exhausted retries.", job, error_code="storage_unavailable")
        return {"outcome": "failed", "error_code": "storage_unavailable"}
    except Exception:
        logger.exception("Unexpected processing failure.", extra={"processing_job_id": job.pk})
        finish_job(
            job.pk,
            status=ProcessingJob.Status.FAILED,
            error_code=ProcessingJob.ErrorCode.PROCESSING_ERROR,
            error_message="Source verification could not be completed safely.",
        )
        return {"outcome": "failed", "error_code": "processing_error"}
    finish_job(job.pk, status=ProcessingJob.Status.SUCCEEDED, result_metadata=result)
    _log("Processing job succeeded.", job, status="succeeded")
    return {"outcome": "succeeded"}


def recover_stale_jobs(*, job_ids=None, dispatch=True):
    now = timezone.now()
    recovered = []
    with transaction.atomic():
        queryset = (
            ProcessingJob.objects.select_for_update()
            .filter(status=ProcessingJob.Status.RUNNING)
            .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now))
        )
        if job_ids is not None:
            queryset = queryset.filter(pk__in=job_ids)
        jobs = list(queryset)
        for job in jobs:
            job.status = ProcessingJob.Status.QUEUED
            job.queued_at = now
            job.started_at = None
            job.heartbeat_at = None
            job.lease_expires_at = None
            job.celery_task_id = ""
            job.last_dispatched_at = None
            job.error_code = ProcessingJob.ErrorCode.WORKER_LOST
            job.error_message = "A worker lease expired; verification was safely re-queued."
            job.save()
            recovered.append(job.pk)
        if dispatch:
            for job_id in recovered:
                transaction.on_commit(lambda job_id=job_id: dispatch_processing_job_safely(job_id))
    return recovered
