"""Visits app admin. Read-mostly, same as journal: bookings are cancelled,
never deleted, so the admin here is for oversight."""

from django.contrib import admin

from .models import Visit


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ["id", "user_name", "kind", "start", "end", "status", "created_at"]
    list_filter = ["kind", "status"]
    search_fields = ["user_name", "note"]
    readonly_fields = ["created_at", "cancelled_at"]
