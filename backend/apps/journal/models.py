"""Journal app models: visit entries, photos, and the tamper-evident trail.

Design intent (see docs/SECURITY_AND_LEGAL.md): nothing here is ever hard-deleted
or silently overwritten. An `Entry` can be edited by its author for a short
window after submission; after that, corrections go in as an `Addendum` and
every edit made during the window is captured as an `EntryRevision`. Photos are
never edited or deleted by visitors at all — only a family admin can soft-delete
one, with a reason, and that action itself is logged to `AuditEvent`.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.users.models import User


class PainSource(models.TextChoices):
    TRAVIS_SAID = "travis_said", "Travis said"
    OBSERVED = "observed", "Observed"


class Trend(models.TextChoices):
    BETTER = "better", "Better than last time"
    SAME = "same", "About the same"
    WORSE = "worse", "Worse than last time"
    UNSURE = "unsure", "Not sure / first visit"


class EntryStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"


class BodyArea(models.TextChoices):
    BRUISING = "bruising", "Bruising"
    ROAD_RASH = "road_rash", "Road rash"
    KNEE_BRACE = "knee_brace", "Knee / brace"
    SHOULDER = "shoulder", "Shoulder"
    RIBS = "ribs", "Ribs"
    OTHER = "other", "Other injury"
    GENERAL = "general", "General / whole visit"


# Prompts and free-text answers live in versioned JSON (`Entry.answers`) rather
# than one column per question, so the questionnaire can grow when the
# attorney asks for something new without a migration. This is the version the
# frontend's `src/config/questionnaire.ts` currently implements; bump both
# together when a section is added or renamed.
QUESTIONNAIRE_VERSION = 1


class Entry(models.Model):
    """One visitor's account of one visit."""

    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="entries")
    # Snapshot so the name on an entry survives an author being renamed later.
    author_name = models.CharField(max_length=255)

    occurred_at = models.DateTimeField(
        default=timezone.now, help_text="When the visit happened, as the author entered it."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    pain_level = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    pain_source = models.CharField(
        max_length=20, choices=PainSource.choices, blank=True
    )
    trend = models.CharField(max_length=20, choices=Trend.choices, blank=True)

    answers = models.JSONField(default=dict, blank=True)
    questionnaire_version = models.PositiveSmallIntegerField(default=QUESTIONNAIRE_VERSION)

    status = models.CharField(
        max_length=20, choices=EntryStatus.choices, default=EntryStatus.DRAFT
    )

    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        verbose_name_plural = "entries"

    def __str__(self) -> str:
        return f"{self.author_name} — {self.occurred_at:%Y-%m-%d %H:%M}"

    @property
    def edit_window(self):
        from datetime import timedelta

        return timedelta(hours=getattr(settings, "ENTRY_EDIT_WINDOW_HOURS", 24))

    @property
    def is_locked(self) -> bool:
        """Past the edit window: further corrections must be addenda, not edits.

        A draft (never submitted) is never locked, so an author can keep working
        on it. The window starts at submission, not creation.
        """
        if self.status != EntryStatus.SUBMITTED or not self.submitted_at:
            return False
        return timezone.now() >= self.submitted_at + self.edit_window

    def snapshot(self) -> dict:
        """Field values worth keeping in a revision when the entry changes."""
        return {
            "occurred_at": self.occurred_at.isoformat(),
            "pain_level": self.pain_level,
            "pain_source": self.pain_source,
            "trend": self.trend,
            "answers": self.answers,
            "status": self.status,
        }


class EntryRevision(models.Model):
    """A snapshot taken every time an entry's content changes, before the change.

    Nothing reads these back into the UI yet in v1 — they exist so a full
    history survives even though the live row is mutable during the edit
    window, for anyone (family, attorney) who later needs to show what changed.
    """

    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="revisions")
    snapshot = models.JSONField()
    edited_at = models.DateTimeField(auto_now_add=True)
    edited_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["edited_at"]


class Addendum(models.Model):
    """A dated correction or add-on, used once an entry is locked (or anytime)."""

    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="addenda")
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    author_name = models.CharField(max_length=255)
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "addenda"


# Each of the three FileFields below needs its own top-level `upload_to`
# function: Django's migration writer serializes these by dotted import path,
# which a closure or a shared function can't provide.
def _entry_photo_path(instance: "Photo", variant: str, filename: str) -> str:
    date = instance.entry.occurred_at or timezone.now()
    return f"journal/{date:%Y/%m}/{instance.entry_id}/{variant}/{filename}"


def original_upload_to(instance: "Photo", filename: str) -> str:
    return _entry_photo_path(instance, "original", filename)


def display_upload_to(instance: "Photo", filename: str) -> str:
    return _entry_photo_path(instance, "display", filename)


def thumb_upload_to(instance: "Photo", filename: str) -> str:
    return _entry_photo_path(instance, "thumb", filename)


class Photo(models.Model):
    """One uploaded photo, kept in three forms.

    `original` is the untouched upload (bytes as received, EXIF intact) — the
    strongest form for authentication and is never regenerated or overwritten.
    `display` and `thumb` are JPEG derivatives (HEIC converted, GPS stripped)
    used for viewing in the app.
    """

    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="photos")
    uploader = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    uploader_name = models.CharField(max_length=255)

    original = models.FileField(upload_to=original_upload_to)
    display = models.FileField(upload_to=display_upload_to)
    thumb = models.FileField(upload_to=thumb_upload_to)

    sha256 = models.CharField(max_length=64, db_index=True)
    size = models.PositiveIntegerField()
    mime = models.CharField(max_length=100)
    exif_taken_at = models.DateTimeField(null=True, blank=True)
    # The device's own "last modified" for the file, informational only — never
    # used as the record of when the photo was taken; that's exif_taken_at or,
    # failing that, uploaded_at.
    client_last_modified = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    body_area = models.CharField(
        max_length=20, choices=BodyArea.choices, default=BodyArea.GENERAL
    )
    caption = models.CharField(max_length=500, blank=True)

    # Soft delete only, and only ever done by family (see permissions.py). The
    # files themselves are left on disk untouched.
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_reason = models.CharField(max_length=500, blank=True)
    deleted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["uploaded_at"]

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class AuditAction(models.TextChoices):
    ENTRY_SUBMITTED = "entry_submitted", "Entry submitted"
    ENTRY_EDITED = "entry_edited", "Entry edited"
    ADDENDUM_ADDED = "addendum_added", "Addendum added"
    PHOTO_UPLOADED = "photo_uploaded", "Photo uploaded"
    PHOTO_DELETED = "photo_deleted", "Photo soft-deleted"


class AuditEvent(models.Model):
    """Append-only record of who did what. Never edited, never deleted."""

    # Kept independent of `actor` (which is nullable) so audit scoping never
    # depends on an actor row still existing.
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    actor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_name = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=40, choices=AuditAction.choices)
    object_type = models.CharField(max_length=40)
    object_id = models.CharField(max_length=40)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.object_type}#{self.object_id}"
