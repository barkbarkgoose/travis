"""Journal app admin. Read-mostly: this data is meant to be append-only, so
the admin here is for oversight, not routine editing.
"""

from django.contrib import admin

from .models import Addendum, AuditEvent, Entry, EntryRevision, Photo


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0
    fields = ["body_area", "caption", "uploader_name", "uploaded_at", "deleted_at"]
    readonly_fields = ["uploader_name", "uploaded_at"]


class AddendumInline(admin.TabularInline):
    model = Addendum
    extra = 0
    fields = ["author_name", "body", "created_at"]
    readonly_fields = ["author_name", "created_at"]


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ["id", "author_name", "occurred_at", "status", "pain_level", "is_locked"]
    list_filter = ["status", "trend"]
    search_fields = ["author_name", "answers"]
    readonly_fields = ["created_at", "updated_at", "is_locked"]
    inlines = [PhotoInline, AddendumInline]


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ["id", "entry", "uploader_name", "body_area", "uploaded_at", "deleted_at"]
    list_filter = ["body_area"]
    readonly_fields = ["sha256", "size", "mime", "uploaded_at"]


@admin.register(EntryRevision)
class EntryRevisionAdmin(admin.ModelAdmin):
    list_display = ["id", "entry", "edited_by", "edited_at"]
    readonly_fields = ["entry", "snapshot", "edited_by", "edited_at"]


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "actor_name", "action", "object_type", "object_id"]
    list_filter = ["action"]
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
