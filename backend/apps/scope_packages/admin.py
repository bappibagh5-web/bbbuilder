from django.contrib import admin

from .models import ScopePackage, ScopePackageSource, ScopePackageVersion


@admin.register(ScopePackage)
class ScopePackageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "project",
        "trade_category",
        "lifecycle",
        "generation_rule_version",
        "source_snapshot",
        "current_version",
    )
    list_filter = ("organization", "project", "lifecycle", "generation_rule_version")
    search_fields = ("project__project_number", "trade_category", "trade_key")
    readonly_fields = tuple(field.name for field in ScopePackage._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ScopePackageVersion)
class ScopePackageVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "package", "version", "status", "created_by", "created_at")
    list_filter = ("status", "created_at")
    readonly_fields = tuple(field.name for field in ScopePackageVersion._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ScopePackageSource)
class ScopePackageSourceAdmin(admin.ModelAdmin):
    list_display = ("id", "package_version", "snapshot_entry", "created_at")
    readonly_fields = tuple(field.name for field in ScopePackageSource._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
