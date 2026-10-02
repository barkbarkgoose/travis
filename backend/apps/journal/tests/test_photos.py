"""Photo upload endpoint and authenticated media serving."""

from datetime import timezone as dt_timezone

import pytest
from django.utils import timezone

from apps.journal.models import AuditEvent, Entry, Photo

from .factories import make_heic_file, make_image_file


def photos_url(entry_pk):
    return f"/api/v1/journal/entries/{entry_pk}/photos/"


def photo_file_url(photo_pk, variant):
    return f"/api/v1/journal/photos/{photo_pk}/{variant}/"


@pytest.fixture
def entry(visitor):
    return Entry.objects.create(author=visitor, author_name=visitor.name)


@pytest.mark.django_db
class TestPhotoUpload:
    def test_visitor_uploads_jpeg_to_own_entry(self, api_client, visitor, entry):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(
            photos_url(entry.pk),
            {"file": make_image_file(), "body_area": "bruising", "caption": "Left forearm"},
            format="multipart",
        )
        assert response.status_code == 201
        assert response.data["body_area"] == "bruising"
        assert response.data["uploader_name"] == "Maria Lopez"
        assert set(response.data["urls"]) == {"original", "display", "thumb"}

        photo = Photo.objects.get()
        assert photo.entry_id == entry.pk
        assert len(photo.sha256) == 64
        assert photo.mime == "image/jpeg"
        assert AuditEvent.objects.filter(action="photo_uploaded").exists()

    def test_heic_upload_is_accepted_and_converted(self, api_client, visitor, entry):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(
            photos_url(entry.pk), {"file": make_heic_file()}, format="multipart"
        )
        assert response.status_code == 201
        photo = Photo.objects.get()
        assert photo.mime == "image/heic"
        assert photo.display.name.endswith(".jpg")

    def test_svg_is_rejected(self, api_client, visitor, entry):
        from django.core.files.uploadedfile import SimpleUploadedFile

        api_client.force_authenticate(user=visitor)
        svg = SimpleUploadedFile(
            "evil.svg", b"<svg><script>alert(1)</script></svg>", content_type="image/svg+xml"
        )
        response = api_client.post(photos_url(entry.pk), {"file": svg}, format="multipart")
        assert response.status_code == 400
        assert Photo.objects.count() == 0

    def test_spoofed_content_type_does_not_bypass_validation(self, api_client, visitor, entry):
        from django.core.files.uploadedfile import SimpleUploadedFile

        api_client.force_authenticate(user=visitor)
        fake = SimpleUploadedFile("photo.jpg", b"not really a jpeg", content_type="image/jpeg")
        response = api_client.post(photos_url(entry.pk), {"file": fake}, format="multipart")
        assert response.status_code == 400

    def test_no_file_is_400(self, api_client, visitor, entry):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(photos_url(entry.pk), {}, format="multipart")
        assert response.status_code == 400

    def test_invalid_body_area_rejected(self, api_client, visitor, entry):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(
            photos_url(entry.pk),
            {"file": make_image_file(), "body_area": "not-a-real-area"},
            format="multipart",
        )
        assert response.status_code == 400

    def test_other_visitor_cannot_upload_to_someone_elses_entry(
        self, api_client, other_visitor, entry
    ):
        api_client.force_authenticate(user=other_visitor)
        response = api_client.post(photos_url(entry.pk), {"file": make_image_file()}, format="multipart")
        assert response.status_code == 403

    def test_upload_allowed_after_entry_is_locked(self, api_client, visitor, entry):
        from datetime import timedelta

        from apps.journal.models import EntryStatus

        entry.status = EntryStatus.SUBMITTED
        entry.submitted_at = timezone.now() - timedelta(hours=48)
        entry.save()

        api_client.force_authenticate(user=visitor)
        response = api_client.post(photos_url(entry.pk), {"file": make_image_file()}, format="multipart")
        assert response.status_code == 201

    def test_client_last_modified_is_parsed(self, api_client, visitor, entry):
        api_client.force_authenticate(user=visitor)
        epoch_ms = 1700000000000
        response = api_client.post(
            photos_url(entry.pk),
            {"file": make_image_file(), "client_last_modified": str(epoch_ms)},
            format="multipart",
        )
        assert response.status_code == 201
        photo = Photo.objects.get()
        assert photo.client_last_modified.replace(tzinfo=dt_timezone.utc).timestamp() == pytest.approx(
            epoch_ms / 1000
        )


@pytest.mark.django_db
class TestPhotoFileAccess:
    def _upload(self, api_client, visitor, entry):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(photos_url(entry.pk), {"file": make_image_file()}, format="multipart")
        return Photo.objects.get(pk=response.data["id"])

    def test_uploader_can_fetch_all_variants(self, api_client, visitor, entry):
        photo = self._upload(api_client, visitor, entry)
        api_client.force_authenticate(user=visitor)
        for variant in ("original", "display", "thumb"):
            response = api_client.get(photo_file_url(photo.pk, variant))
            assert response.status_code == 200, variant

    def test_family_can_fetch_any_photo(self, api_client, visitor, entry, family_user):
        photo = self._upload(api_client, visitor, entry)
        api_client.force_authenticate(user=family_user)
        assert api_client.get(photo_file_url(photo.pk, "display")).status_code == 200

    def test_unrelated_visitor_is_forbidden(self, api_client, visitor, entry, other_visitor):
        photo = self._upload(api_client, visitor, entry)
        api_client.force_authenticate(user=other_visitor)
        response = api_client.get(photo_file_url(photo.pk, "display"))
        assert response.status_code == 403

    def test_unauthenticated_is_401(self, api_client, visitor, entry):
        photo = self._upload(api_client, visitor, entry)
        api_client.force_authenticate(user=None)
        response = api_client.get(photo_file_url(photo.pk, "display"))
        assert response.status_code == 401

    def test_unknown_variant_is_404(self, api_client, visitor, entry):
        photo = self._upload(api_client, visitor, entry)
        api_client.force_authenticate(user=visitor)
        response = api_client.get(photo_file_url(photo.pk, "medium"))
        assert response.status_code == 404

    def test_soft_deleted_photo_is_hidden_from_uploader(self, api_client, visitor, entry):
        photo = self._upload(api_client, visitor, entry)
        photo.deleted_at = timezone.now()
        photo.deleted_reason = "duplicate"
        photo.save()

        api_client.force_authenticate(user=visitor)
        assert api_client.get(photo_file_url(photo.pk, "display")).status_code == 404

    def test_soft_deleted_photo_still_visible_to_family(self, api_client, visitor, entry, family_user):
        photo = self._upload(api_client, visitor, entry)
        photo.deleted_at = timezone.now()
        photo.save()

        api_client.force_authenticate(user=family_user)
        assert api_client.get(photo_file_url(photo.pk, "display")).status_code == 200

    def test_deleted_photo_excluded_from_entry_serialization_for_visitor(
        self, api_client, visitor, entry
    ):
        photo = self._upload(api_client, visitor, entry)
        photo.deleted_at = timezone.now()
        photo.save()

        api_client.force_authenticate(user=visitor)
        response = api_client.get(f"/api/v1/journal/entries/{entry.pk}/")
        assert response.data["photos"] == []

    def test_photo_in_another_organization_is_404(self, api_client, other_org_visitor, visitor, entry):
        photo = self._upload(api_client, visitor, entry)
        api_client.force_authenticate(user=other_org_visitor)
        response = api_client.get(photo_file_url(photo.pk, "display"))
        assert response.status_code == 404
