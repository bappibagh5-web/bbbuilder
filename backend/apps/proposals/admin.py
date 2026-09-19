from django.contrib import admin

from .models import (
    Estimate,
    EstimateAllowance,
    EstimateAlternate,
    EstimateExclusion,
    EstimateFinancialAdjustment,
    EstimateLine,
    EstimateVersion,
    Proposal,
    ProposalVersion,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Estimate)
class EstimateAdmin(ReadOnlyAdmin):
    list_display = ("id", "project", "title", "created_by", "created_at")


@admin.register(EstimateVersion)
class EstimateVersionAdmin(ReadOnlyAdmin):
    list_display = ("id", "estimate", "version", "status", "created_by", "created_at")


@admin.register(Proposal)
class ProposalAdmin(ReadOnlyAdmin):
    list_display = ("id", "project", "title", "estimate", "client_contact", "created_at")


@admin.register(ProposalVersion)
class ProposalVersionAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "proposal",
        "version",
        "status",
        "estimate_version",
        "created_at",
    )


for model in (
    EstimateLine,
    EstimateAllowance,
    EstimateAlternate,
    EstimateExclusion,
    EstimateFinancialAdjustment,
):
    admin.site.register(model, ReadOnlyAdmin)
