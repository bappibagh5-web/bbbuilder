import hashlib
from decimal import Decimal

import pymupdf
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse

from apps.documents.models import FileAsset
from apps.documents.storage import ObjectStorageError, get_object_storage
from apps.projects.audit import record_event

from .models import ProposalPdfArtifact, ProposalVersion
from .services import _require_operator

TEMPLATE_VERSION = "client-proposal-v2"


def _pdf_safe_text(value):
    """Replace punctuation unsupported by the portable PDF Base-14 font."""
    return str(value).translate(
        str.maketrans(
            {
                "—": "-",
                "–": "-",
                "•": "-",
                "·": "|",
                "“": '"',
                "”": '"',
                "‘": "'",
                "’": "'",
                "\u00a0": " ",
            }
        )
    )


def _money(value):
    return f"{Decimal(str(value)):,.2f}"


def _lines(version):
    client = version.client_project_snapshot
    money = version.commercial_snapshot
    address = client.get("site_address", {})
    location = ", ".join(
        filter(
            None,
            [
                address.get("line_1"),
                address.get("city"),
                address.get("province_state"),
                address.get("postal_zip_code"),
            ],
        )
    )
    rows = [
        client.get("organization_legal_name") or client.get("organization_name") or "BB Builders",
        "CLIENT PROPOSAL",
        f"Proposal: {version.proposal_number} | Version {version.version}",
        f"Issue date: {client.get('issue_date', '')}",
        "",
        f"Prepared for: {client.get('client_name', '')}",
        f"Project: {client.get('project_number', '')} | {client.get('project_name', '')}",
        f"Site: {location}",
        "",
        "Proposal Summary",
        version.introduction,
        version.scope_summary,
    ]
    if money.get("allowances"):
        rows += ["", "Included Allowances"] + [
            f"- {item['description']} - {item['currency']} {_money(item['amount'])}"
            for item in money["allowances"]
        ]
    if money.get("alternates"):
        rows += ["", "Included Options / Alternates"] + [
            f"- {item['description']} - {item['direction'].upper()} "
            f"{item['currency']} {_money(item['amount'])}"
            for item in money["alternates"]
        ]
    if money.get("exclusions"):
        rows += ["", "Exclusions"] + [f"- {item['description']}" for item in money["exclusions"]]
    rows += [
        "",
        "Financial Summary",
        f"Pre-tax: {money['currency']} {_money(money['pre_tax_amount'])}",
        f"Tax: {money['currency']} {_money(money['tax_amount'])}",
        f"Proposed Contract Amount: {money['currency']} {_money(money['total_amount'])}",
    ]
    if version.commercial_notes:
        rows += ["", "Commercial Notes", version.commercial_notes]
    if version.terms_conditions:
        rows += ["", "Terms and Conditions", version.terms_conditions]
    rows += ["", "FINALIZED - This proposal has not been accepted or awarded."]
    return [_pdf_safe_text(row) for row in rows]


def render_pdf(version):
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    y = 48
    for row in _lines(version):
        if y > 740:
            page = document.new_page(width=612, height=792)
            y = 48
        rect = pymupdf.Rect(48, y, 564, y + 60)
        font_size = 16 if row in {"CLIENT PROPOSAL", "Financial Summary"} else 10
        used = page.insert_textbox(
            rect, row or " ", fontsize=font_size, fontname="helv", color=(0.08, 0.2, 0.32)
        )
        y += max(18, 60 - max(used, 0))
    return document.tobytes(garbage=4, deflate=True)


@transaction.atomic
def generate_final_pdf(*, version, actor):
    _require_operator(actor=actor, organization=version.proposal.organization)
    locked = (
        ProposalVersion.objects.select_for_update()
        .select_related("proposal__organization", "proposal__project")
        .get(pk=version.pk)
    )
    if locked.status != ProposalVersion.Status.FINALIZED:
        raise ValidationError("Only a finalized proposal can generate a final PDF.")
    existing = ProposalPdfArtifact.objects.filter(
        proposal_version=locked, template_version=TEMPLATE_VERSION
    ).first()
    if existing:
        return existing, False
    payload = render_pdf(locked)
    checksum = hashlib.sha256(payload).hexdigest()
    key = (
        f"organizations/{locked.proposal.organization_id}/"
        f"projects/{locked.proposal.project_id}/proposals/{locked.pk}/{checksum}.pdf"
    )
    storage = get_object_storage()
    storage.save(key, ContentFile(payload), len(payload))
    try:
        asset = FileAsset.objects.create(
            organization=locked.proposal.organization,
            bucket=settings.AWS_STORAGE_BUCKET_NAME,
            storage_key=key,
            original_filename=f"{locked.proposal_number}-V{locked.version}.pdf",
            declared_mime_type="application/pdf",
            detected_mime_type="application/pdf",
            byte_size=len(payload),
            checksum=checksum,
            created_by=actor,
        )
        artifact = ProposalPdfArtifact.objects.create(
            proposal_version=locked,
            file_asset=asset,
            template_version=TEMPLATE_VERSION,
            version=(ProposalPdfArtifact.objects.filter(proposal_version=locked).count() + 1),
            generated_by=actor,
        )
    except Exception:
        storage.delete(key)
        raise
    record_event(
        organization=locked.proposal.organization,
        project=locked.proposal.project,
        actor=actor,
        action_code="proposal.pdf_generated",
        target=artifact,
        metadata={
            "proposal_version_id": locked.pk,
            "file_asset_id": asset.pk,
            "template_version": TEMPLATE_VERSION,
            "artifact_version": artifact.version,
        },
    )
    return artifact, True


def download_response(artifact):
    try:
        stored = get_object_storage().open(artifact.file_asset.storage_key)
    except ObjectStorageError as error:
        raise ValidationError("The final proposal PDF is unavailable.") from error
    if stored is None:
        raise ValidationError("The final proposal PDF is unavailable.")
    response = FileResponse(
        stored,
        as_attachment=True,
        filename=artifact.file_asset.original_filename,
        content_type="application/pdf",
    )
    response["Content-Length"] = artifact.file_asset.byte_size
    return response
