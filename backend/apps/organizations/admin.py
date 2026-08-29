from django.contrib import admin

from .models import Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "default_timezone", "updated_at")
    list_filter = ("status",)
    search_fields = ("name", "legal_name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_active", "starts_at", "ends_at")
    list_filter = ("role", "is_active", "organization")
    search_fields = ("user__email", "organization__name")
    autocomplete_fields = ("user", "organization")
