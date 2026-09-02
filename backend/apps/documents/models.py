from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.organizations.models import Organization
from apps.projects.models import Project


class ImmutableFieldsMixin(models.Model):
    immutable_fields: tuple[str, ...] = ()

    class Meta:
        abstract = True

    def _validate_immutable_fields(self):
        if not self.pk:
            return
        original = type(self).objects.filter(pk=self.pk).values(*self.immutable_fields).first()
        if original is None:
            return
        changed = {
            field: "This field is immutable after creation."
            for field in self.immutable_fields
            if original[field] != getattr(self, field)
        }
        if changed:
            raise ValidationError(changed)

    def save(self, *args, **kwargs):
        self._validate_immutable_fields()
        self.full_clean()
        return super().save(*args, **kwargs)


class FileAsset(ImmutableFieldsMixin):
    class StorageBackend(models.TextChoices):
        S3 = "s3", "S3-compatible object storage"

    class ChecksumAlgorithm(models.TextChoices):
        SHA256 = "sha256", "SHA-256"
        SHA512 = "sha512", "SHA-512"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="file_assets"
    )
    storage_backend = models.CharField(
        max_length=20, choices=StorageBackend, default=StorageBackend.S3
    )
    bucket = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=1024, unique=True)
    original_filename = models.CharField(max_length=500)
    declared_mime_type = models.CharField(max_length=255, blank=True)
    detected_mime_type = models.CharField(max_length=255, blank=True)
    byte_size = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    checksum_algorithm = models.CharField(
        max_length=20, choices=ChecksumAlgorithm, default=ChecksumAlgorithm.SHA256
    )
    checksum = models.CharField(max_length=128)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_file_assets",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "organization_id",
        "storage_backend",
        "bucket",
        "storage_key",
        "original_filename",
        "declared_mime_type",
        "detected_mime_type",
        "byte_size",
        "checksum_algorithm",
        "checksum",
        "created_by_id",
        "created_at",
    )

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("organization", "checksum_algorithm", "checksum"))]

    def clean(self):
        super().clean()
        expected_length = {
            self.ChecksumAlgorithm.SHA256: 64,
            self.ChecksumAlgorithm.SHA512: 128,
        }.get(self.checksum_algorithm)
        checksum = self.checksum.lower()
        if expected_length and (
            len(checksum) != expected_length
            or any(character not in "0123456789abcdef" for character in checksum)
        ):
            raise ValidationError(
                {"checksum": f"Enter a {expected_length}-character hexadecimal checksum."}
            )
        self.checksum = checksum

    def __str__(self):
        return self.original_filename


class ProjectFile(ImmutableFieldsMixin):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="project_files")
    file_asset = models.OneToOneField(
        FileAsset, on_delete=models.PROTECT, related_name="project_file"
    )
    display_name = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_project_files",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = ("project_id", "file_asset_id", "created_by_id", "created_at")

    class Meta:
        ordering = ("-created_at", "-id")

    def clean(self):
        super().clean()
        if (
            self.project_id
            and self.file_asset_id
            and self.project.organization_id != self.file_asset.organization_id
        ):
            raise ValidationError(
                {"file_asset": "The file asset and project must belong to the same organization."}
            )

    def __str__(self):
        return self.display_name or self.file_asset.original_filename


class Document(ImmutableFieldsMixin):
    class Category(models.TextChoices):
        DRAWINGS = "drawings", "Drawings"
        SPECIFICATIONS = "specifications", "Specifications"
        ADDENDUM = "addendum", "Addendum"
        CLIENT_SCOPE = "client_scope", "Client scope"
        LANDLORD_REQUIREMENTS = "landlord_requirements", "Landlord requirements"
        RESPONSIBILITY_SCHEDULE = "responsibility_schedule", "Responsibility schedule"
        BID_REQUIREMENTS = "bid_requirements", "Bid requirements / form"
        SCHEDULE = "schedule", "Schedule"
        SPREADSHEET = "spreadsheet", "Spreadsheet"
        IMAGE_REFERENCE = "image_reference", "Image / reference"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

    class Discipline(models.TextChoices):
        GENERAL = "general", "General"
        ARCHITECTURAL = "architectural", "Architectural"
        STRUCTURAL = "structural", "Structural"
        CIVIL = "civil", "Civil"
        MECHANICAL = "mechanical", "Mechanical"
        PLUMBING = "plumbing", "Plumbing"
        ELECTRICAL = "electrical", "Electrical"
        FIRE_PROTECTION = "fire_protection", "Fire protection"
        INTERIORS = "interiors", "Interiors"
        LANDSCAPE = "landscape", "Landscape"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="documents")
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=40, choices=Category, default=Category.UNKNOWN)
    discipline = models.CharField(max_length=40, choices=Discipline, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    current_revision = models.ForeignKey(
        "DocumentRevision",
        on_delete=models.PROTECT,
        related_name="current_for_documents",
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    immutable_fields = (
        "project_id",
        "current_revision_id",
        "created_by_id",
        "created_at",
    )

    class Meta:
        ordering = ("title", "id")

    def clean(self):
        super().clean()
        if self.current_revision_id and self.current_revision.document_id != self.pk:
            raise ValidationError(
                {"current_revision": "The current revision must belong to this document."}
            )

    def __str__(self):
        return self.title


class DocumentRevision(ImmutableFieldsMixin):
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="revisions")
    project_file = models.OneToOneField(
        ProjectFile, on_delete=models.PROTECT, related_name="document_revision"
    )
    revision_label = models.CharField(max_length=100, blank=True)
    issued_date = models.DateField(blank=True, null=True)
    received_at = models.DateTimeField(default=timezone.now)
    source_filename = models.CharField(max_length=500)
    notes = models.TextField(blank=True)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="superseded_by",
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_document_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "document_id",
        "project_file_id",
        "revision_label",
        "issued_date",
        "received_at",
        "source_filename",
        "notes",
        "supersedes_id",
        "created_by_id",
        "created_at",
    )

    class Meta:
        ordering = ("-received_at", "-id")

    def clean(self):
        super().clean()
        if (
            self.document_id
            and self.project_file_id
            and self.document.project_id != self.project_file.project_id
        ):
            raise ValidationError(
                {"project_file": "The revision file must belong to the document's project."}
            )
        if self.supersedes_id:
            if self.supersedes_id == self.pk:
                raise ValidationError({"supersedes": "A revision cannot supersede itself."})
            if self.document_id and self.supersedes.document_id != self.document_id:
                raise ValidationError(
                    {"supersedes": "A revision can supersede only a revision of the same document."}
                )

    def __str__(self):
        return f"{self.document.title} — {self.revision_label or self.pk or 'new revision'}"


class DocumentPage(ImmutableFieldsMixin):
    class Rotation(models.IntegerChoices):
        DEGREES_0 = 0, "0 degrees"
        DEGREES_90 = 90, "90 degrees"
        DEGREES_180 = 180, "180 degrees"
        DEGREES_270 = 270, "270 degrees"

    document_revision = models.ForeignKey(
        DocumentRevision,
        on_delete=models.PROTECT,
        related_name="pages",
    )
    page_number = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    page_label = models.TextField(blank=True)
    width_points = models.FloatField(validators=[MinValueValidator(0.01)])
    height_points = models.FloatField(validators=[MinValueValidator(0.01)])
    rotation_degrees = models.PositiveSmallIntegerField(
        choices=Rotation,
        default=Rotation.DEGREES_0,
    )
    native_text = models.TextField(blank=True)
    native_text_char_count = models.PositiveIntegerField(default=0)
    has_native_text = models.BooleanField(default=False)
    parser_name = models.CharField(max_length=100)
    parser_version = models.CharField(max_length=100)
    indexed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "document_revision_id",
        "page_number",
        "page_label",
        "width_points",
        "height_points",
        "rotation_degrees",
        "native_text",
        "native_text_char_count",
        "has_native_text",
        "parser_name",
        "parser_version",
        "indexed_at",
        "created_at",
    )

    class Meta:
        ordering = ("document_revision_id", "page_number")
        constraints = [
            models.UniqueConstraint(
                fields=("document_revision", "page_number"),
                name="documents_unique_revision_page_number",
            )
        ]
        indexes = [models.Index(fields=("document_revision", "page_number"))]

    def clean(self):
        super().clean()
        meaningful_text = bool(self.native_text.strip())
        if self.native_text_char_count != len(self.native_text):
            raise ValidationError(
                {"native_text_char_count": "Character count must match the stored native text."}
            )
        if self.has_native_text != meaningful_text:
            raise ValidationError(
                {"has_native_text": "Native-text availability must match the stored native text."}
            )

    def __str__(self):
        return f"{self.document_revision} — page {self.page_number}"


class DrawingSheet(ImmutableFieldsMixin):
    class ExtractionMethod(models.TextChoices):
        PAGE_LABEL = "page_label", "PDF page label"
        NATIVE_TEXT = "native_text", "Native PDF text"

    class Quality(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"

    page = models.OneToOneField(
        DocumentPage,
        on_delete=models.PROTECT,
        related_name="drawing_sheet",
    )
    sheet_number = models.CharField(max_length=50, blank=True)
    sheet_title = models.CharField(max_length=255, blank=True)
    extraction_method = models.CharField(max_length=30, choices=ExtractionMethod)
    quality = models.CharField(max_length=20, choices=Quality)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "page_id",
        "sheet_number",
        "sheet_title",
        "extraction_method",
        "quality",
        "created_at",
    )

    class Meta:
        ordering = ("page__document_revision_id", "page__page_number")

    def clean(self):
        super().clean()
        if not self.sheet_number and not self.sheet_title:
            raise ValidationError(
                "A drawing-sheet candidate requires a sheet number or sheet title."
            )

    def __str__(self):
        return self.sheet_number or self.sheet_title or f"Page {self.page.page_number}"
