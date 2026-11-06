"""Users app admin."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import redirect

from .models import Invite, Passkey, User


def _passkey_admin_login(request, extra_context=None):
    """Replace the admin's password form: staff sign in to the app with a passkey,
    and the app's /admin-signin page opens the admin session (AdminSessionView)."""
    return redirect("/admin-signin")


admin.site.login = _passkey_admin_login


class PasskeyInline(admin.TabularInline):
    """Deleting a family member's passkeys here lets them sign in with their password
    again to set up a new one (e.g. after losing their phone)."""

    model = Passkey
    extra = 0
    can_delete = True
    fields = ["name", "created_at", "last_used_at"]
    readonly_fields = fields


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["id", "name", "email", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active", "is_staff", "organization"]
    search_fields = ["email", "name"]
    ordering = ["-created_at"]
    inlines = [PasskeyInline]
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
