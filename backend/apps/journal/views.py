"""Journal app views: entries, addenda, photo upload, and authenticated media."""

from __future__ import annotations

from datetime import datetime as dt_datetime, timezone as dt_timezone

from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsFamily

from .audit import log_audit
from .models import (
    Addendum,
    AuditAction,
    AuditEvent,
    BodyArea,
    Entry,
    EntryRevision,
    EntryStatus,
    Photo,
    QUESTIONNAIRE_VERSION,
)
from .permissions import IsEntryAuthorOrFamilyReadOnly
from .serializers import (
    AddendumSerializer,
    AuditEventSerializer,
    EntrySerializer,
    EntryWriteSerializer,
    PhotoSerializer,
    answers_has_content,
)
from .uploads import UploadRejected, process_upload

PHOTO_EXTENSION_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/heic": "heic",
    "image/webp": "webp",
}


def _org_entries(user):
    return Entry.objects.filter(author__organization=user.organization)


def _entry_has_minimal_content(entry: Entry) -> bool:
    """The bar for submitting: at least a note, a pain level, or a photo."""
    if entry.pain_level is not None:
        return True
    if entry.photos.filter(deleted_at__isnull=True).exists():
        return True
    return answers_has_content(entry.answers)


class EntryListCreateView(generics.ListCreateAPIView):
    """GET lists the caller's own entries (family can pass `?all=1` for
    everyone in the organization). POST creates a new draft entry."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = _org_entries(self.request.user).select_related("author").prefetch_related(
            "photos", "addenda"
        )
        if self.request.query_params.get("all") and self.request.user.is_family:
            return qs
        return qs.filter(author=self.request.user)

    def get_serializer_class(self):
        return EntrySerializer if self.request.method == "GET" else EntryWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = serializer.save(
            author=request.user,
            author_name=request.user.name,
            questionnaire_version=QUESTIONNAIRE_VERSION,
        )
        out = EntrySerializer(entry, context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)


class EntryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET: the author or any family account. PATCH: the author only, and
    only before the entry locks — see `Entry.is_locked`. DELETE: the author
    only, and only while it's still a draft — see `destroy()`."""

    permission_classes = [IsAuthenticated, IsEntryAuthorOrFamilyReadOnly]

    def get_queryset(self):
        return _org_entries(self.request.user).select_related("author").prefetch_related(
            "photos", "addenda"
        )

    def get_serializer_class(self):
        return EntrySerializer if self.request.method == "GET" else EntryWriteSerializer

    def update(self, request, *args, **kwargs):
        entry = self.get_object()  # runs has_object_permission
        if entry.is_locked:
            return Response(
                {
                    "detail": "This entry is locked. Add an addendum instead of "
                    "editing it directly."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(entry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Snapshot the pre-edit state so the change is recoverable later.
        EntryRevision.objects.create(
            entry=entry, snapshot=entry.snapshot(), edited_by=request.user
        )
        serializer.save()
        log_audit(actor=request.user, action=AuditAction.ENTRY_EDITED, obj=entry, request=request)

        out = EntrySerializer(entry, context=self.get_serializer_context())
        return Response(out.data)

    def destroy(self, request, *args, **kwargs):
        """Drafts pile up (every "Log a visit" starts a fresh one), so a
        visitor can discard one outright — unlike a submitted entry, a draft
        was never part of the record, so this isn't a spoliation concern the
        way deleting real evidence would be (see docs/SECURITY_AND_LEGAL.md).
        Once submitted, the only way to remove or correct something is an
        addendum: this path stays closed for good.
        """
        entry = self.get_object()  # runs has_object_permission (author-only for writes)
        if entry.status != EntryStatus.DRAFT:
            return Response(
                {
                    "detail": "Submitted entries can't be deleted — they're part of "
                    "the record. Add an addendum instead."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Draft photos were never submitted either, so clear their files from
        # storage too rather than leaving them orphaned on disk.
        for photo in entry.photos.all():
            photo.original.delete(save=False)
            photo.display.delete(save=False)
            photo.thumb.delete(save=False)

        entry.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EntrySubmitView(APIView):
    """Marks a draft as submitted, starting the edit-window clock."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        entry = get_object_or_404(_org_entries(request.user), pk=pk)
        if entry.author_id != request.user.id:
            raise PermissionDenied("Only the person who wrote this entry can submit it.")
        if entry.status == EntryStatus.SUBMITTED:
            return Response(
                {"detail": "This entry has already been submitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not _entry_has_minimal_content(entry):
            return Response(
                {"detail": "Add a note, a pain level, or a photo before submitting."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        entry.status = EntryStatus.SUBMITTED
        entry.submitted_at = timezone.now()
        entry.save(update_fields=["status", "submitted_at"])
        log_audit(actor=request.user, action=AuditAction.ENTRY_SUBMITTED, obj=entry, request=request)

        return Response(EntrySerializer(entry, context={"request": request}).data)


class AddendumCreateView(APIView):
    """Anyone who can see the entry (its author, or family) can add a dated
    correction or follow-up — allowed any time, locked or not."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        entry = get_object_or_404(_org_entries(request.user), pk=pk)
        if not (entry.author_id == request.user.id or request.user.is_family):
            raise PermissionDenied("You can't add to this entry.")

        serializer = AddendumSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        addendum = Addendum.objects.create(
            entry=entry,
            author=request.user,
            author_name=request.user.name,
            body=serializer.validated_data["body"],
        )
        log_audit(actor=request.user, action=AuditAction.ADDENDUM_ADDED, obj=entry, request=request)

        return Response(AddendumSerializer(addendum).data, status=status.HTTP_201_CREATED)


class PhotoUploadView(APIView):
    """Only the entry's author uploads to it — consistent with every photo
    needing a named, accountable photographer (see docs/SECURITY_AND_LEGAL.md).
    Allowed any time, including after the entry locks: a new photo never
    rewrites history, it only adds to it.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        entry = get_object_or_404(_org_entries(request.user), pk=pk)
        if entry.author_id != request.user.id:
            raise PermissionDenied("Only the person who wrote this entry can add photos to it.")

        uploaded = request.FILES.get("file")
        if not uploaded:
            raise ValidationError({"file": "No file was uploaded."})

        body_area = request.data.get("body_area") or BodyArea.GENERAL
        if body_area not in BodyArea.values:
            raise ValidationError({"body_area": "Not a recognized body area."})
        caption = str(request.data.get("caption") or "").strip()[:500]

        client_last_modified = None
        raw_lm = request.data.get("client_last_modified")
        if raw_lm:
            try:
                client_last_modified = dt_datetime.fromtimestamp(
                    float(raw_lm) / 1000, tz=dt_timezone.utc
                )
            except (TypeError, ValueError, OverflowError, OSError):
                client_last_modified = None

        try:
            processed = process_upload(uploaded.read())
        except UploadRejected as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        photo = Photo(
            entry=entry,
            uploader=request.user,
            uploader_name=request.user.name,
            sha256=processed.sha256,
            size=processed.size,
            mime=processed.mime,
            exif_taken_at=processed.exif_taken_at,
            client_last_modified=client_last_modified,
            body_area=body_area,
            caption=caption,
        )
        extension = PHOTO_EXTENSION_BY_MIME.get(processed.mime, "bin")
        # Filenames are derived from the hash, never the client's filename —
        # nothing about the stored path is attacker- or accident-controlled.
        photo.original.save(
            f"{processed.sha256}.{extension}",
            ContentFile(processed.original_bytes),
            save=False,
        )
        photo.display.save(f"{processed.sha256}-display.jpg", processed.display, save=False)
        photo.thumb.save(f"{processed.sha256}-thumb.jpg", processed.thumb, save=False)
        photo.save()

        log_audit(
            actor=request.user,
            action=AuditAction.PHOTO_UPLOADED,
            obj=photo,
            metadata={"sha256": processed.sha256, "size": processed.size, "entry_id": entry.id},
            request=request,
        )

        return Response(
            PhotoSerializer(photo, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class PhotoFileView(APIView):
    """Streams one photo variant. There is no public media URL — every request
    here is checked: the uploader or any family account, nobody else.
    """

    permission_classes = [IsAuthenticated]
    VARIANTS = {"original", "display", "thumb"}

    def get(self, request, pk, variant):
        if variant not in self.VARIANTS:
            raise Http404

        photo = get_object_or_404(
            Photo.objects.select_related("entry__author__organization", "uploader"), pk=pk
        )
        if photo.entry.author.organization_id != request.user.organization_id:
            raise Http404
        if photo.is_deleted and not request.user.is_family:
            raise Http404
        if not (photo.uploader_id == request.user.id or request.user.is_family):
            raise PermissionDenied("You don't have access to this photo.")

        field = getattr(photo, variant)
        if not field:
            raise Http404

        content_type = photo.mime if variant == "original" else "image/jpeg"
        response = FileResponse(field.open("rb"), content_type=content_type)
        response["Content-Disposition"] = f'inline; filename="{variant}-{photo.pk}.{field.name.rsplit(".", 1)[-1]}"'
        # Media is behind auth, never CDN/browser-shared: cache in this
        # browser only, and let a proxy know not to cache it for anyone else.
        response["Cache-Control"] = "private, max-age=3600"
        return response


class AuditListView(generics.ListAPIView):
    """Family-only: the append-only trail of edits, addenda, and photo actions."""

    serializer_class = AuditEventSerializer
    permission_classes = [IsFamily]

    def get_queryset(self):
        return AuditEvent.objects.filter(organization=self.request.user.organization)
