"""Entry CRUD, the edit window, addenda, and visibility rules."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.journal.models import (
    Addendum,
    AuditEvent,
    Entry,
    EntryRevision,
    EntryStatus,
    Photo,
)

from .factories import make_image_file

ENTRIES_URL = "/api/v1/journal/entries/"


def entry_url(pk):
    return f"/api/v1/journal/entries/{pk}/"


def submit_url(pk):
    return f"/api/v1/journal/entries/{pk}/submit/"


def addenda_url(pk):
    return f"/api/v1/journal/entries/{pk}/addenda/"


def photos_url(pk):
    return f"/api/v1/journal/entries/{pk}/photos/"


@pytest.mark.django_db
class TestCreateEntry:
    def test_requires_auth(self, api_client):
        assert api_client.post(ENTRIES_URL, {}, format="json").status_code == 401

    def test_visitor_creates_draft(self, api_client, visitor):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(
            ENTRIES_URL,
            {"pain_level": 6, "pain_source": "observed", "answers": {"overall_note": "Resting."}},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["status"] == "draft"
        assert response.data["author_name"] == "Maria Lopez"
        assert response.data["is_locked"] is False
        assert response.data["answers"] == {"overall_note": "Resting."}

    def test_unknown_answer_keys_are_dropped(self, api_client, visitor):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(
            ENTRIES_URL,
            {"answers": {"overall_note": "ok", "__proto__": "x", "extra_junk": "y"}},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["answers"] == {"overall_note": "ok"}

    def test_answer_text_is_length_bounded(self, api_client, visitor):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(
            ENTRIES_URL, {"answers": {"who_else_was_there": "x" * 5000}}, format="json"
        )
        assert response.status_code == 201
        assert len(response.data["answers"]["who_else_was_there"]) == 300

    def test_answers_must_be_an_object(self, api_client, visitor):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(ENTRIES_URL, {"answers": "not an object"}, format="json")
        assert response.status_code == 400

    def test_pain_level_out_of_range_rejected(self, api_client, visitor):
        api_client.force_authenticate(user=visitor)
        response = api_client.post(ENTRIES_URL, {"pain_level": 11}, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestListEntries:
    def test_visitor_sees_only_their_own(self, api_client, visitor, other_visitor):
        Entry.objects.create(author=visitor, author_name=visitor.name)
        Entry.objects.create(author=other_visitor, author_name=other_visitor.name)

        api_client.force_authenticate(user=visitor)
        response = api_client.get(ENTRIES_URL)

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["author_name"] == "Maria Lopez"

    def test_family_sees_only_own_without_all_flag(self, api_client, family_user, visitor):
        Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=family_user)
        response = api_client.get(ENTRIES_URL)
        assert response.data["count"] == 0

    def test_family_sees_everyone_with_all_flag(self, api_client, family_user, visitor, other_visitor):
        Entry.objects.create(author=visitor, author_name=visitor.name)
        Entry.objects.create(author=other_visitor, author_name=other_visitor.name)
        api_client.force_authenticate(user=family_user)
        response = api_client.get(ENTRIES_URL, {"all": "1"})
        assert response.data["count"] == 2

    def test_visitor_cannot_use_all_flag(self, api_client, visitor, other_visitor):
        Entry.objects.create(author=visitor, author_name=visitor.name)
        Entry.objects.create(author=other_visitor, author_name=other_visitor.name)
        api_client.force_authenticate(user=visitor)
        response = api_client.get(ENTRIES_URL, {"all": "1"})
        assert response.data["count"] == 1

    def test_entries_in_another_organization_are_invisible(
        self, api_client, family_user, other_org_visitor
    ):
        Entry.objects.create(author=other_org_visitor, author_name=other_org_visitor.name)
        api_client.force_authenticate(user=family_user)
        response = api_client.get(ENTRIES_URL, {"all": "1"})
        assert response.data["count"] == 0


@pytest.mark.django_db
class TestRetrieveAndEditEntry:
    def test_author_can_view_own(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=visitor)
        assert api_client.get(entry_url(entry.pk)).status_code == 200

    def test_family_can_view_any(self, api_client, family_user, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=family_user)
        assert api_client.get(entry_url(entry.pk)).status_code == 200

    def test_other_visitor_cannot_view(self, api_client, visitor, other_visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=other_visitor)
        response = api_client.get(entry_url(entry.pk))
        assert response.status_code in (403, 404)

    def test_author_can_edit_draft(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=visitor)
        response = api_client.patch(entry_url(entry.pk), {"pain_level": 4}, format="json")
        assert response.status_code == 200
        assert response.data["pain_level"] == 4

    def test_edit_creates_revision_and_audit_row(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name, pain_level=3)
        api_client.force_authenticate(user=visitor)
        api_client.patch(entry_url(entry.pk), {"pain_level": 5}, format="json")

        revision = EntryRevision.objects.get(entry=entry)
        assert revision.snapshot["pain_level"] == 3  # pre-edit value

        event = AuditEvent.objects.get(action="entry_edited")
        assert event.actor == visitor
        assert event.object_id == str(entry.pk)

    def test_family_cannot_edit_someone_elses_entry(self, api_client, family_user, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=family_user)
        response = api_client.patch(entry_url(entry.pk), {"pain_level": 9}, format="json")
        assert response.status_code == 403

    def test_other_visitor_cannot_edit(self, api_client, visitor, other_visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=other_visitor)
        response = api_client.patch(entry_url(entry.pk), {"pain_level": 9}, format="json")
        assert response.status_code in (403, 404)

    def test_locked_entry_rejects_edit(self, api_client, visitor):
        entry = Entry.objects.create(
            author=visitor,
            author_name=visitor.name,
            status=EntryStatus.SUBMITTED,
            submitted_at=timezone.now() - timedelta(hours=25),
        )
        api_client.force_authenticate(user=visitor)
        response = api_client.patch(entry_url(entry.pk), {"pain_level": 9}, format="json")
        assert response.status_code == 403
        entry.refresh_from_db()
        assert entry.pain_level is None

    def test_within_window_entry_is_still_editable(self, api_client, visitor):
        entry = Entry.objects.create(
            author=visitor,
            author_name=visitor.name,
            status=EntryStatus.SUBMITTED,
            submitted_at=timezone.now() - timedelta(hours=1),
        )
        api_client.force_authenticate(user=visitor)
        response = api_client.patch(entry_url(entry.pk), {"pain_level": 9}, format="json")
        assert response.status_code == 200

    def test_draft_is_never_locked_regardless_of_age(self, api_client, visitor):
        entry = Entry.objects.create(
            author=visitor,
            author_name=visitor.name,
            occurred_at=timezone.now() - timedelta(days=30),
        )
        assert entry.is_locked is False

    def test_can_edit_reflects_the_viewer_not_just_the_entry(self, api_client, visitor, family_user):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)

        api_client.force_authenticate(user=visitor)
        assert api_client.get(entry_url(entry.pk)).data["can_edit"] is True

        api_client.force_authenticate(user=family_user)
        assert api_client.get(entry_url(entry.pk)).data["can_edit"] is False

    def test_can_edit_false_once_locked(self, api_client, visitor):
        entry = Entry.objects.create(
            author=visitor,
            author_name=visitor.name,
            status=EntryStatus.SUBMITTED,
            submitted_at=timezone.now() - timedelta(hours=25),
        )
        api_client.force_authenticate(user=visitor)
        response = api_client.get(entry_url(entry.pk))
        assert response.data["can_edit"] is False
        assert response.data["edit_window_ends_at"] is not None

    def test_edit_window_ends_at_null_for_draft(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=visitor)
        response = api_client.get(entry_url(entry.pk))
        assert response.data["edit_window_ends_at"] is None


@pytest.mark.django_db
class TestDeleteEntry:
    def test_requires_auth(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        assert api_client.delete(entry_url(entry.pk)).status_code == 401

    def test_author_can_delete_own_draft(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=visitor)
        response = api_client.delete(entry_url(entry.pk))
        assert response.status_code == 204
        assert not Entry.objects.filter(pk=entry.pk).exists()

    def test_deleting_a_draft_removes_its_photo_files_from_storage(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=visitor)
        upload = api_client.post(photos_url(entry.pk), {"file": make_image_file()}, format="multipart")
        photo = Photo.objects.get(pk=upload.data["id"])
        storage = photo.original.storage
        names = [photo.original.name, photo.display.name, photo.thumb.name]
        assert all(storage.exists(name) for name in names)

        response = api_client.delete(entry_url(entry.pk))
        assert response.status_code == 204
        assert not Photo.objects.filter(pk=photo.pk).exists()
        assert not any(storage.exists(name) for name in names)

    def test_submitted_entry_cannot_be_deleted(self, api_client, visitor):
        entry = Entry.objects.create(
            author=visitor,
            author_name=visitor.name,
            pain_level=3,
            status=EntryStatus.SUBMITTED,
            submitted_at=timezone.now(),
        )
        api_client.force_authenticate(user=visitor)
        response = api_client.delete(entry_url(entry.pk))
        assert response.status_code == 403
        assert Entry.objects.filter(pk=entry.pk).exists()

    def test_locked_entry_cannot_be_deleted(self, api_client, visitor):
        entry = Entry.objects.create(
            author=visitor,
            author_name=visitor.name,
            pain_level=3,
            status=EntryStatus.SUBMITTED,
            submitted_at=timezone.now() - timedelta(hours=48),
        )
        api_client.force_authenticate(user=visitor)
        response = api_client.delete(entry_url(entry.pk))
        assert response.status_code == 403
        assert Entry.objects.filter(pk=entry.pk).exists()

    def test_other_visitor_cannot_delete(self, api_client, visitor, other_visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=other_visitor)
        response = api_client.delete(entry_url(entry.pk))
        assert response.status_code in (403, 404)
        assert Entry.objects.filter(pk=entry.pk).exists()

    def test_family_cannot_delete_someone_elses_draft(self, api_client, family_user, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=family_user)
        response = api_client.delete(entry_url(entry.pk))
        assert response.status_code == 403
        assert Entry.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
class TestSubmitEntry:
    def test_empty_entry_cannot_be_submitted(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=visitor)
        response = api_client.post(submit_url(entry.pk))
        assert response.status_code == 400
        entry.refresh_from_db()
        assert entry.status == EntryStatus.DRAFT

    def test_entry_with_a_note_can_be_submitted(self, api_client, visitor):
        entry = Entry.objects.create(
            author=visitor, author_name=visitor.name, answers={"overall_note": "Doing okay."}
        )
        api_client.force_authenticate(user=visitor)
        response = api_client.post(submit_url(entry.pk))
        assert response.status_code == 200
        assert response.data["status"] == "submitted"
        assert response.data["submitted_at"] is not None
        assert AuditEvent.objects.filter(action="entry_submitted", object_id=str(entry.pk)).exists()

    def test_entry_with_just_a_pain_level_can_be_submitted(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name, pain_level=0)
        api_client.force_authenticate(user=visitor)
        assert api_client.post(submit_url(entry.pk)).status_code == 200

    def test_cannot_submit_twice(self, api_client, visitor):
        entry = Entry.objects.create(
            author=visitor,
            author_name=visitor.name,
            pain_level=2,
            status=EntryStatus.SUBMITTED,
            submitted_at=timezone.now(),
        )
        api_client.force_authenticate(user=visitor)
        response = api_client.post(submit_url(entry.pk))
        assert response.status_code == 400

    def test_only_author_can_submit(self, api_client, visitor, other_visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name, pain_level=2)
        api_client.force_authenticate(user=other_visitor)
        response = api_client.post(submit_url(entry.pk))
        assert response.status_code == 403
        entry.refresh_from_db()
        assert entry.status == EntryStatus.DRAFT


@pytest.mark.django_db
class TestAddenda:
    def test_author_can_addend_a_locked_entry(self, api_client, visitor):
        entry = Entry.objects.create(
            author=visitor,
            author_name=visitor.name,
            status=EntryStatus.SUBMITTED,
            submitted_at=timezone.now() - timedelta(hours=48),
        )
        api_client.force_authenticate(user=visitor)
        response = api_client.post(
            addenda_url(entry.pk), {"body": "Correction: it was his right knee."}, format="json"
        )
        assert response.status_code == 201
        assert Addendum.objects.filter(entry=entry).count() == 1
        assert AuditEvent.objects.filter(action="addendum_added").exists()

    def test_family_can_addend_any_entry(self, api_client, family_user, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=family_user)
        response = api_client.post(addenda_url(entry.pk), {"body": "Note from family."}, format="json")
        assert response.status_code == 201
        assert response.data["author_name"] == "Family Admin"

    def test_unrelated_visitor_cannot_addend(self, api_client, visitor, other_visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=other_visitor)
        response = api_client.post(addenda_url(entry.pk), {"body": "hi"}, format="json")
        assert response.status_code == 403

    def test_empty_addendum_rejected(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=visitor)
        response = api_client.post(addenda_url(entry.pk), {"body": "   "}, format="json")
        assert response.status_code == 400

    def test_addendum_appears_on_entry_read(self, api_client, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        api_client.force_authenticate(user=visitor)
        api_client.post(addenda_url(entry.pk), {"body": "Follow-up note."}, format="json")

        response = api_client.get(entry_url(entry.pk))
        assert len(response.data["addenda"]) == 1
        assert response.data["addenda"][0]["body"] == "Follow-up note."
