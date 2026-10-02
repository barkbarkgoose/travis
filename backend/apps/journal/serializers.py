"""Journal app serializers."""

from __future__ import annotations

from rest_framework import serializers
from rest_framework.reverse import reverse

from .models import Addendum, AuditEvent, Entry, Photo

# Whitelist of free-text answer keys and their max lengths. Mirrors
# `frontend/src/config/questionnaire.ts` — keep the two in sync when a
# question is added, renamed, or removed. Unknown keys are silently dropped,
# same pattern as `UserSettingsSerializer` in apps.users.
#
# `photo_notes` is required by the frontend before an entry can be submitted
# (see the "Photos & notes" step); the server doesn't re-enforce that itself,
# since a visitor with photos but no notes yet is still a valid draft.
# `additional_notes` is the single catch-all that replaced separate
# surgeries/treatments/difficulties fields — fewer, more natural free-text
# prompts read as more credible than several short fragments (see
# docs/SECURITY_AND_LEGAL.md).
ANSWER_FIELD_MAX_LENGTHS: dict[str, int] = {
    "who_else_was_there": 300,
    "overall_note": 2000,
    "alertness_mood": 500,
    "photo_notes": 2000,
    "additional_notes": 3000,
}


def sanitize_answers(value) -> dict:
    """Whitelist and length-bound the free-text questionnaire answers."""
    if not isinstance(value, dict):
        raise serializers.ValidationError("Answers must be a JSON object.")

    clean: dict = {}
    for key, max_length in ANSWER_FIELD_MAX_LENGTHS.items():
        if key in value and value[key] is not None:
            clean[key] = str(value[key]).strip()[:max_length]

    return clean


def answers_has_content(answers: dict) -> bool:
    return any(str(val or "").strip() for val in (answers or {}).values())


class AddendumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Addendum
        fields = ["id", "author_name", "body", "created_at"]
        read_only_fields = ["id", "author_name", "created_at"]

    def validate_body(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Addendum can't be empty.")
        return cleaned


class PhotoSerializer(serializers.ModelSerializer):
    urls = serializers.SerializerMethodField()

    class Meta:
        model = Photo
        fields = [
            "id",
            "uploader_name",
            "uploaded_at",
            "exif_taken_at",
            "body_area",
            "caption",
            "urls",
        ]

    def get_urls(self, obj: Photo) -> dict:
        request = self.context.get("request")
        return {
            variant: reverse(
                "journal:photo-file",
                kwargs={"pk": obj.pk, "variant": variant},
                request=request,
            )
            for variant in ("display", "thumb", "original")
        }


class EntrySerializer(serializers.ModelSerializer):
    """Read representation: includes computed lock state and nested children."""

    is_locked = serializers.BooleanField(read_only=True)
    can_edit = serializers.SerializerMethodField()
    edit_window_ends_at = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    addenda = AddendumSerializer(many=True, read_only=True)

    class Meta:
        model = Entry
        fields = [
            "id",
            "author_name",
            "occurred_at",
            "created_at",
            "updated_at",
            "submitted_at",
            "is_locked",
            "can_edit",
            "edit_window_ends_at",
            "pain_level",
            "pain_source",
            "trend",
            "answers",
            "questionnaire_version",
            "status",
            "photos",
            "addenda",
        ]
        read_only_fields = fields

    def get_can_edit(self, obj: Entry) -> bool:
        """Whether the *current* viewer can PATCH this entry right now — mirrors
        `IsEntryAuthorOrFamilyReadOnly` plus the lock check in the view, so the
        frontend doesn't have to reimplement that logic to decide what to show.
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        return user.id == obj.author_id and not obj.is_locked

    def get_edit_window_ends_at(self, obj: Entry):
        if not obj.submitted_at:
            return None
        return obj.submitted_at + obj.edit_window

    def get_photos(self, obj: Entry) -> list:
        request = self.context.get("request")
        qs = obj.photos.all()
        # A soft-deleted photo drops out of view for everyone except family,
        # who may need it to explain the deletion (see AuditEvent).
        if not (request and getattr(request.user, "is_family", False)):
            qs = qs.filter(deleted_at__isnull=True)
        return PhotoSerializer(qs, many=True, context=self.context).data


class EntryWriteSerializer(serializers.ModelSerializer):
    """Create/update representation: only the fields a visitor can set."""

    answers = serializers.JSONField(required=False)

    class Meta:
        model = Entry
        fields = ["occurred_at", "pain_level", "pain_source", "trend", "answers"]

    def validate_answers(self, value) -> dict:
        return sanitize_answers(value)


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "actor_name",
            "action",
            "object_type",
            "object_id",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields
