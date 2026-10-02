"""Users app admin."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Invite, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["id", "name", "email", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active", "is_staff", "organization"]
    search_fields = ["email", "name"]
    ordering = ["-created_at"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name", "role", "organization")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "name",
                    "role",
                    "password1",
                    "password2",
                    "organization",
                ),
            },
        ),
    )


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ["id", "organization", "created_by", "created_at", "revoked_at"]
    readonly_fields = ["token", "created_at"]
