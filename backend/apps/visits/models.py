"""Visits app models: the booking calendar that replaces the sign-up sheet.

Nothing here is hard-deleted either, in the same spirit as the journal app —
cancelling a booking sets a status rather than removing the row, so the
calendar's own history (who signed up, who cancelled and when) survives.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.users.models import User


class VisitKind(models.TextChoices):
    VISIT = "visit", "Visit"
    # Family-only: reserves a range (e.g. "surgery 10am, no visits") without
    # attributing it to a visitor.
    BLOCKED = "blocked", "Blocked"


class VisitStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    CANCELLED = "cancelled", "Cancelled"


class Visit(models.Model):
    """One slot on the calendar: a visitor's booking, or a family block."""

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="visits")
    # Snapshot so the name shown on a past booking survives the user being
    # renamed later, same reasoning as Entry.author_name.
    user_name = models.CharField(max_length=255)

    start = models.DateTimeField()
    end = models.DateTimeField()
    note = models.CharField(max_length=300, blank=True)

    kind = models.CharField(max_length=20, choices=VisitKind.choices, default=VisitKind.VISIT)
    status = models.CharField(
        max_length=20, choices=VisitStatus.choices, default=VisitStatus.PLANNED
    )

    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["start"]

    def __str__(self) -> str:
        label = self.get_kind_display() if self.kind == VisitKind.BLOCKED else self.user_name
        return f"{label} — {self.start:%Y-%m-%d %H:%M}"

    @property
    def is_past(self) -> bool:
        return self.end <= timezone.now()
