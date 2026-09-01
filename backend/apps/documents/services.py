from django.core.exceptions import ValidationError
from django.db import transaction

from apps.projects.audit import record_event

from .models import Document, DocumentRevision


@transaction.atomic
def set_current_revision(*, document: Document, revision: DocumentRevision | None, actor):
    locked_document = Document.objects.select_for_update().get(pk=document.pk)
    if revision is not None and revision.document_id != locked_document.pk:
        raise ValidationError("The current revision must belong to this document.")

    previous_id = locked_document.current_revision_id
    next_id = revision.pk if revision else None
    if previous_id == next_id:
        return locked_document

    Document.objects.filter(pk=locked_document.pk).update(current_revision_id=next_id)
    locked_document.current_revision_id = next_id
    record_event(
        organization=locked_document.project.organization,
        project=locked_document.project,
        actor=actor,
        action_code="document.current_revision_changed",
        target=locked_document,
        metadata={"before_revision_id": previous_id, "after_revision_id": next_id},
    )
    return locked_document
