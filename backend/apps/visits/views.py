"""Visits app views: the booking calendar.

Deliberately small — one model, a few endpoints, an agenda-style UI on the
frontend with no calendar library (see the project plan). The one piece of
real logic is the capacity rule in `_check_availability`.
"""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Visit, VisitKind, VisitStatus
from .permissions import IsVisitOwnerOrFamily
from .serializers import VisitSerializer, VisitWriteSerializer


class VisitConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "That time isn't available."
    default_code = "visit_conflict"


def _org_visits(user):
    return Visit.objects.filter(user__organization=user.organization)


def _parse_range_param(value):
    """Best-effort ISO-8601 parse for the `from`/`to` query params. Returns
    None on anything unparseable rather than 500ing on a malformed value."""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_default_timezone())
    return parsed


def _overlapping(qs, start, end):
    return qs.filter(start__lt=end, end__gt=start)


def _check_availability(user, *, start, end, exclude_pk=None):
    """Raises VisitConflict if `start`–`end` can't be booked as a normal
    visit: either it overlaps a family block, or it would push the number of
    concurrent visitors past MAX_CONCURRENT_VISITORS.
    """
    qs = _org_visits(user).filter(status=VisitStatus.PLANNED)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    overlapping = _overlapping(qs, start, end)

    if overlapping.filter(kind=VisitKind.BLOCKED).exists():
        raise VisitConflict("That time is blocked off — no visits then.")

    concurrent = overlapping.filter(kind=VisitKind.VISIT).count()
    limit = getattr(settings, "MAX_CONCURRENT_VISITORS", 3)
    if concurrent >= limit:
        raise VisitConflict(
            f"Only {limit} visitors can be there at once, and that time is full."
        )


class VisitListCreateView(generics.ListCreateAPIView):
    """GET lists bookings in the organization, optionally narrowed to a
    `?from=&to=` window (both ISO-8601). POST creates a booking (or, for
    family accounts, a block)."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = _org_visits(self.request.user).select_related("user")
        start = _parse_range_param(self.request.query_params.get("from"))
        end = _parse_range_param(self.request.query_params.get("to"))
        if start and end:
            qs = _overlapping(qs, start, end)
        return qs

    def get_serializer_class(self):
        return VisitSerializer if self.request.method == "GET" else VisitWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        kind = serializer.validated_data.get("kind") or VisitKind.VISIT
        if kind == VisitKind.BLOCKED and not request.user.is_family:
            raise PermissionDenied("Only family accounts can block time.")

        if kind == VisitKind.VISIT:
            _check_availability(
                request.user,
                start=serializer.validated_data["start"],
                end=serializer.validated_data["end"],
            )

        visit = serializer.save(user=request.user, user_name=request.user.name, kind=kind)
        out = VisitSerializer(visit, context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)


class VisitDetailView(generics.RetrieveUpdateAPIView):
    """GET: anyone in the organization. PATCH: the visitor who booked it, or
    family — reschedules or renotes an existing, non-cancelled booking."""

    permission_classes = [IsAuthenticated, IsVisitOwnerOrFamily]

    def get_queryset(self):
        return _org_visits(self.request.user).select_related("user")

    def get_serializer_class(self):
        return VisitSerializer if self.request.method == "GET" else VisitWriteSerializer

    def update(self, request, *args, **kwargs):
        visit = self.get_object()  # runs has_object_permission
        if visit.status == VisitStatus.CANCELLED:
            return Response(
                {"detail": "This booking was cancelled. Book a new time instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(visit, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        kind = serializer.validated_data.get("kind", visit.kind)
        if kind == VisitKind.BLOCKED and not request.user.is_family:
            raise PermissionDenied("Only family accounts can block time.")

        if kind == VisitKind.VISIT:
            _check_availability(
                request.user,
                start=serializer.validated_data.get("start", visit.start),
                end=serializer.validated_data.get("end", visit.end),
                exclude_pk=visit.pk,
            )

        serializer.save()
        return Response(VisitSerializer(visit, context=self.get_serializer_context()).data)


class VisitCancelView(APIView):
    """Cancels a booking — sets a status rather than deleting the row, so the
    slot's history (who booked it, who cancelled) survives."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        visit = get_object_or_404(_org_visits(request.user), pk=pk)
        if not (visit.user_id == request.user.id or request.user.is_family):
            raise PermissionDenied("You can't cancel this booking.")
        if visit.status == VisitStatus.CANCELLED:
            return Response(
                {"detail": "This booking is already cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        visit.status = VisitStatus.CANCELLED
        visit.cancelled_at = timezone.now()
        visit.save(update_fields=["status", "cancelled_at"])

        return Response(VisitSerializer(visit, context={"request": request}).data)
