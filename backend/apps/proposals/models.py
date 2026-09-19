from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.documents.models import ImmutableFieldsMixin
from apps.organizations.models import Organization
from apps.projects.models import Project, ProjectContact


class Estimate(ImmutableFieldsMixin):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="estimates"
    )
    project = models.OneToOneField(Project, on_delete=models.PROTECT, related_name="estimate")
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_estimates"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = ("organization_id", "project_id", "title", "created_by_id")

    class Meta:
        ordering = ("project_id", "id")

    def clean(self):
        super().clean()
        if self.project_id and self.organization_id != self.project.organization_id:
            raise ValidationError({"organization": "Estimate organization must match its project."})

    def __str__(self):
        return f"{self.project} — {self.title}"


class EstimateVersion(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"

    estimate = models.ForeignKey(Estimate, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="successor",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_estimate_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "estimate_id",
        "version",
        "supersedes_id",
        "status",
        "created_by_id",
    )

    class Meta:
        ordering = ("estimate_id", "version")
        constraints = [
            models.UniqueConstraint(
                fields=("estimate", "version"), name="unique_estimate_version_number"
            ),
            models.CheckConstraint(condition=Q(version__gt=0), name="estimate_version_positive"),
        ]

    def clean(self):
        super().clean()
        if self.supersedes_id:
            if self.supersedes.estimate_id != self.estimate_id:
                raise ValidationError({"supersedes": "A predecessor must belong to this estimate."})
            if self.supersedes.version >= self.version:
                raise ValidationError({"supersedes": "A predecessor must be an earlier version."})

    def __str__(self):
        return f"{self.estimate} V{self.version}"


class Proposal(ImmutableFieldsMixin):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="proposals"
    )
    project = models.OneToOneField(Project, on_delete=models.PROTECT, related_name="proposal")
    estimate = models.OneToOneField(Estimate, on_delete=models.PROTECT, related_name="proposal")
    title = models.CharField(max_length=255)
    client_contact = models.ForeignKey(
        ProjectContact,
        on_delete=models.PROTECT,
        related_name="proposals",
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_proposals"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "organization_id",
        "project_id",
        "estimate_id",
        "title",
        "client_contact_id",
        "created_by_id",
    )

    class Meta:
        ordering = ("project_id", "id")

    def clean(self):
        super().clean()
        errors = {}
        if self.project_id and self.organization_id != self.project.organization_id:
            errors["organization"] = "Proposal organization must match its project."
        if self.estimate_id and self.estimate.project_id != self.project_id:
            errors["estimate"] = "Proposal estimate must belong to its project."
        if self.client_contact_id and self.client_contact.project_id != self.project_id:
            errors["client_contact"] = "Proposal contact must belong to its project."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.project} — {self.title}"


class ProposalVersion(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"

    proposal = models.ForeignKey(Proposal, on_delete=models.PROTECT, related_name="versions")
    estimate_version = models.ForeignKey(
        EstimateVersion, on_delete=models.PROTECT, related_name="proposal_versions"
    )
    version = models.PositiveIntegerField()
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="successor",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_proposal_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "proposal_id",
        "estimate_version_id",
        "version",
        "supersedes_id",
        "status",
        "created_by_id",
    )

    class Meta:
        ordering = ("proposal_id", "version")
        constraints = [
            models.UniqueConstraint(
                fields=("proposal", "version"), name="unique_proposal_version_number"
            ),
            models.CheckConstraint(condition=Q(version__gt=0), name="proposal_version_positive"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.estimate_version_id
            and self.proposal_id
            and self.estimate_version.estimate_id != self.proposal.estimate_id
        ):
            errors["estimate_version"] = "Proposal version must use its proposal's estimate."
        if self.supersedes_id:
            if self.supersedes.proposal_id != self.proposal_id:
                errors["supersedes"] = "A predecessor must belong to this proposal."
            elif self.supersedes.version >= self.version:
                errors["supersedes"] = "A predecessor must be an earlier version."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.proposal} V{self.version}"


class EstimateLine(ImmutableFieldsMixin):
    class LineType(models.TextChoices):
        SOURCE_BASE_BID = "source_base_bid", "Selected contractor base bid"
        M3_LEVELING = "m3_leveling", "BB Builders bid-leveling adjustment"

    class Direction(models.TextChoices):
        ADD = "add", "Add"
        DEDUCT = "deduct", "Deduct"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    project = models.ForeignKey(Project, on_delete=models.PROTECT)
    estimate_version = models.ForeignKey(
        EstimateVersion, on_delete=models.PROTECT, related_name="source_lines"
    )
    line_type = models.CharField(max_length=30, choices=LineType)
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    direction = models.CharField(max_length=10, choices=Direction, default=Direction.ADD)
    included = models.BooleanField(default=True)
    sequence = models.PositiveIntegerField()
    source_human_review = models.ForeignKey(
        "outreach.BidHumanReview", on_delete=models.PROTECT, related_name="estimate_lines"
    )
    source_comparison_entry = models.ForeignKey(
        "outreach.BidComparisonEntry", on_delete=models.PROTECT, related_name="estimate_lines"
    )
    source_bid_revision = models.ForeignKey(
        "outreach.BidRevision", on_delete=models.PROTECT, related_name="estimate_lines"
    )
    source_scope_version = models.ForeignKey(
        "scope_packages.ScopePackageVersion",
        on_delete=models.PROTECT,
        related_name="estimate_lines",
    )
    source_company = models.ForeignKey(
        "contractors.Company", on_delete=models.PROTECT, related_name="estimate_lines"
    )
    source_leveling_adjustment = models.ForeignKey(
        "outreach.BidLevelingAdjustment",
        on_delete=models.PROTECT,
        related_name="estimate_lines",
        blank=True,
        null=True,
    )
    company_name_snapshot = models.CharField(max_length=255)
    trade_snapshot = models.CharField(max_length=255)
    source_category_snapshot = models.CharField(max_length=80, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_estimate_lines"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "organization_id",
        "project_id",
        "estimate_version_id",
        "line_type",
        "description",
        "amount",
        "currency",
        "direction",
        "included",
        "sequence",
        "source_human_review_id",
        "source_comparison_entry_id",
        "source_bid_revision_id",
        "source_scope_version_id",
        "source_company_id",
        "source_leveling_adjustment_id",
        "company_name_snapshot",
        "trade_snapshot",
        "source_category_snapshot",
        "created_by_id",
    )

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("estimate_version", "sequence"), name="unique_estimate_line_sequence"
            ),
            models.UniqueConstraint(
                fields=("estimate_version", "source_human_review"),
                condition=Q(line_type="source_base_bid"),
                name="unique_estimate_selected_review",
            ),
            models.UniqueConstraint(
                fields=("estimate_version", "source_leveling_adjustment"),
                condition=Q(source_leveling_adjustment__isnull=False),
                name="unique_estimate_leveling_source",
            ),
            models.CheckConstraint(
                condition=Q(amount__gte=0), name="estimate_line_amount_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(sequence__gt=0), name="estimate_line_sequence_positive"
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        version = self.estimate_version
        review = self.source_human_review
        entry = self.source_comparison_entry
        revision = self.source_bid_revision
        if (
            self.organization_id != version.estimate.organization_id
            or self.project_id != version.estimate.project_id
        ):
            errors["estimate_version"] = "Estimate line must match its estimate project."
        if len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
            errors["currency"] = "Enter a three-letter uppercase currency code."
        if (
            review.project_id != self.project_id
            or entry.comparison_id != review.comparison_id
            or revision.pk != entry.revision_id
            or self.source_scope_version_id != review.scope_version_id
            or self.source_company_id != entry.company_id
        ):
            errors["source_human_review"] = "Source references must describe one exact selection."
        if self.line_type == self.LineType.SOURCE_BASE_BID:
            if self.source_leveling_adjustment_id or self.direction != self.Direction.ADD:
                errors["line_type"] = "Base-bid lines cannot be leveling adjustments or deductions."
        elif not self.source_leveling_adjustment_id:
            errors["source_leveling_adjustment"] = "A leveling line requires its exact adjustment."
        elif self.source_leveling_adjustment.entry_id != entry.pk:
            errors["source_leveling_adjustment"] = (
                "Leveling adjustment must belong to the selected entry."
            )
        if errors:
            raise ValidationError(errors)


class EstimateAllowance(models.Model):
    class Treatment(models.TextChoices):
        INCLUDED = "included", "Included"
        EXCLUDED = "excluded", "Excluded"

    estimate_version = models.ForeignKey(
        EstimateVersion, on_delete=models.PROTECT, related_name="allowances"
    )
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=3, blank=True)
    treatment = models.CharField(max_length=20, choices=Treatment)
    sequence = models.PositiveIntegerField()
    source_bid_revision = models.ForeignKey(
        "outreach.BidRevision", on_delete=models.PROTECT, blank=True, null=True
    )
    source_commercial_item = models.ForeignKey(
        "outreach.BidCommercialItem", on_delete=models.PROTECT, blank=True, null=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_estimate_allowances",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_estimate_allowances",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("estimate_version", "sequence"), name="unique_estimate_allowance_sequence"
            ),
            models.CheckConstraint(
                condition=Q(amount__isnull=True) | Q(amount__gte=0),
                name="estimate_allowance_amount_nonnegative",
            ),
        ]


class EstimateAlternate(models.Model):
    class Direction(models.TextChoices):
        ADD = "add", "Add"
        DEDUCT = "deduct", "Deduct"

    estimate_version = models.ForeignKey(
        EstimateVersion, on_delete=models.PROTECT, related_name="alternates"
    )
    description = models.CharField(max_length=500)
    direction = models.CharField(max_length=10, choices=Direction)
    amount = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=3, blank=True)
    included_in_estimate = models.BooleanField(default=False)
    source_included_in_base = models.BooleanField(blank=True, null=True)
    sequence = models.PositiveIntegerField()
    source_bid_revision = models.ForeignKey(
        "outreach.BidRevision", on_delete=models.PROTECT, blank=True, null=True
    )
    source_commercial_item = models.ForeignKey(
        "outreach.BidCommercialItem", on_delete=models.PROTECT, blank=True, null=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_estimate_alternates",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_estimate_alternates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("estimate_version", "sequence"), name="unique_estimate_alternate_sequence"
            ),
            models.CheckConstraint(
                condition=Q(amount__isnull=True) | Q(amount__gte=0),
                name="estimate_alternate_amount_nonnegative",
            ),
        ]


class EstimateExclusion(models.Model):
    estimate_version = models.ForeignKey(
        EstimateVersion, on_delete=models.PROTECT, related_name="exclusions"
    )
    description = models.CharField(max_length=500)
    sequence = models.PositiveIntegerField()
    source_bid_revision = models.ForeignKey(
        "outreach.BidRevision", on_delete=models.PROTECT, blank=True, null=True
    )
    source_commercial_item = models.ForeignKey(
        "outreach.BidCommercialItem", on_delete=models.PROTECT, blank=True, null=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_estimate_exclusions",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_estimate_exclusions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("estimate_version", "sequence"), name="unique_estimate_exclusion_sequence"
            )
        ]


class EstimateFinancialAdjustment(models.Model):
    class Category(models.TextChoices):
        MARKUP = "markup", "Markup"
        OVERHEAD = "overhead", "Overhead"
        PROFIT = "profit", "Profit"
        CONTINGENCY = "contingency", "Contingency"
        TAX = "tax", "Tax"
        OTHER = "other", "Other"

    class Method(models.TextChoices):
        FIXED_AMOUNT = "fixed_amount", "Fixed amount"
        PERCENTAGE = "percentage", "Percentage"

    class Basis(models.TextChoices):
        DIRECT_COST = "direct_cost", "Normalized direct cost"
        RUNNING_SUBTOTAL = "running_subtotal", "Running subtotal"
        PRE_TAX_SUBTOTAL = "pre_tax_subtotal", "Pre-tax subtotal"

    estimate_version = models.ForeignKey(
        EstimateVersion, on_delete=models.PROTECT, related_name="financial_adjustments"
    )
    category = models.CharField(max_length=20, choices=Category)
    description = models.CharField(max_length=500)
    method = models.CharField(max_length=20, choices=Method)
    basis = models.CharField(max_length=30, choices=Basis)
    fixed_amount = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    percentage_rate = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    calculated_amount = models.DecimalField(max_digits=18, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=3)
    sequence = models.PositiveIntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_estimate_financial_adjustments",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_estimate_financial_adjustments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("estimate_version", "sequence"), name="unique_estimate_adjustment_sequence"
            ),
            models.CheckConstraint(
                condition=Q(fixed_amount__isnull=True) | Q(fixed_amount__gte=0),
                name="estimate_adjustment_fixed_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(percentage_rate__isnull=True) | Q(percentage_rate__gte=0),
                name="estimate_adjustment_rate_nonnegative",
            ),
        ]
