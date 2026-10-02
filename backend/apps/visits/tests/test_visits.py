"""Booking CRUD, the capacity rule, blocks, cancellation, and visibility."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.visits.models import Visit, VisitKind, VisitStatus

VISITS_URL = "/api/v1/visits/"


def visit_url(pk):
    return f"/api/v1/visits/{pk}/"


def cancel_url(pk):
    return f"/api/v1/visits/{pk}/cancel/"


def slot(hours_from_now=1, duration_minutes=60):
    start = timezone.now() + timedelta(hours=hours_from_now)
    end = start + timedelta(minutes=duration_minutes)
    return start, end


def iso(dt):
    return dt.isoformat()


@pytest.mark.django_db
class TestCreateVisit:
    def test_requires_auth(self, api_client):
        assert api_client.post(VISITS_URL, {}, format="json").status_code == 401

    def test_visitor_books_a_slot(self, api_client, visitor):
        api_client.force_authenticate(user=visitor)
        start, end = slot()
        response = api_client.post(
            VISITS_URL, {"start": iso(start), "end": iso(end), "note": "Bringing snacks"}, format="json"
        )
        assert response.status_code == 201
        assert response.data["kind"] == "visit"
        assert response.data["status"] == "planned"
        assert response.data["user_name"] == "Maria Lopez"
        visit = Visit.objects.get(pk=response.data["id"])
        assert visit.user_id == visitor.id

    def test_end_before_start_is_rejected(self, api_client, visitor):
        api_client.force_authenticate(user=visitor)
        start, end = slot()
        response = api_client.post(
            VISITS_URL, {"start": iso(end), "end": iso(start)}, format="json"
        )
        assert response.status_code == 400

    def test_visitor_cannot_create_a_block(self, api_client, visitor):
        api_client.force_authenticate(user=visitor)
        start, end = slot()
        response = api_client.post(
            VISITS_URL, {"start": iso(start), "end": iso(end), "kind": "blocked"}, format="json"
        )
        assert response.status_code == 403
        assert not Visit.objects.filter(kind=VisitKind.BLOCKED).exists()

    def test_family_can_create_a_block(self, api_client, family_user):
        api_client.force_authenticate(user=family_user)
        start, end = slot()
        response = api_client.post(
            VISITS_URL,
            {"start": iso(start), "end": iso(end), "note": "Surgery", "kind": "blocked"},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["kind"] == "blocked"


@pytest.mark.django_db
class TestCapacityRule:
    def test_fourth_overlapping_booking_is_rejected(
        self, api_client, visitor, other_visitor, third_visitor, fourth_visitor
    ):
        start, end = slot()
        for user in (visitor, other_visitor, third_visitor):
            api_client.force_authenticate(user=user)
            response = api_client.post(
                VISITS_URL, {"start": iso(start), "end": iso(end)}, format="json"
            )
            assert response.status_code == 201

        api_client.force_authenticate(user=fourth_visitor)
        response = api_client.post(VISITS_URL, {"start": iso(start), "end": iso(end)}, format="json")
        assert response.status_code == 409

    def test_non_overlapping_bookings_are_unaffected_by_capacity(
        self, api_client, visitor, other_visitor, third_visitor, fourth_visitor
    ):
        start, end = slot()
        for user in (visitor, other_visitor, third_visitor):
            api_client.force_authenticate(user=user)
            api_client.post(VISITS_URL, {"start": iso(start), "end": iso(end)}, format="json")

        api_client.force_authenticate(user=fourth_visitor)
        later_start, later_end = slot(hours_from_now=5)
        response = api_client.post(
            VISITS_URL, {"start": iso(later_start), "end": iso(later_end)}, format="json"
        )
        assert response.status_code == 201

    def test_cancelled_booking_frees_the_slot(self, api_client, visitor, other_visitor, third_visitor, fourth_visitor):
        start, end = slot()
        visits = []
        for user in (visitor, other_visitor, third_visitor):
            api_client.force_authenticate(user=user)
            response = api_client.post(
                VISITS_URL, {"start": iso(start), "end": iso(end)}, format="json"
            )
            visits.append(response.data["id"])

        api_client.force_authenticate(user=visitor)
        assert api_client.post(cancel_url(visits[0])).status_code == 200

        api_client.force_authenticate(user=fourth_visitor)
        response = api_client.post(VISITS_URL, {"start": iso(start), "end": iso(end)}, format="json")
        assert response.status_code == 201

    def test_blocked_range_rejects_a_booking(self, api_client, visitor, family_user):
        start, end = slot()
        api_client.force_authenticate(user=family_user)
        block = api_client.post(
            VISITS_URL, {"start": iso(start), "end": iso(end), "kind": "blocked"}, format="json"
        )
        assert block.status_code == 201

        api_client.force_authenticate(user=visitor)
        response = api_client.post(VISITS_URL, {"start": iso(start), "end": iso(end)}, format="json")
        assert response.status_code == 409

    def test_blocked_range_partial_overlap_also_rejected(self, api_client, visitor, family_user):
        start, end = slot(hours_from_now=2, duration_minutes=120)
        api_client.force_authenticate(user=family_user)
        api_client.post(
            VISITS_URL, {"start": iso(start), "end": iso(end), "kind": "blocked"}, format="json"
        )

        api_client.force_authenticate(user=visitor)
        overlap_start = start - timedelta(minutes=30)
        overlap_end = start + timedelta(minutes=30)
        response = api_client.post(
            VISITS_URL, {"start": iso(overlap_start), "end": iso(overlap_end)}, format="json"
        )
        assert response.status_code == 409


@pytest.mark.django_db
class TestListVisibility:
    def test_visitor_sees_org_visits_not_other_orgs(self, api_client, visitor, other_org_visitor):
        start, end = slot()
        Visit.objects.create(user=visitor, user_name=visitor.name, start=start, end=end)
        Visit.objects.create(
            user=other_org_visitor, user_name=other_org_visitor.name, start=start, end=end
        )

        api_client.force_authenticate(user=visitor)
        response = api_client.get(VISITS_URL)
        assert response.status_code == 200
        names = {v["user_name"] for v in response.data["results"]}
        assert names == {visitor.name}

    def test_from_to_window_filters_to_overlapping_visits(self, api_client, visitor):
        near_start, near_end = slot(hours_from_now=1)
        far_start, far_end = slot(hours_from_now=100)
        Visit.objects.create(user=visitor, user_name=visitor.name, start=near_start, end=near_end)
        Visit.objects.create(user=visitor, user_name=visitor.name, start=far_start, end=far_end)

        api_client.force_authenticate(user=visitor)
        window_start = near_start - timedelta(hours=1)
        window_end = near_end + timedelta(hours=1)
        response = api_client.get(VISITS_URL, {"from": iso(window_start), "to": iso(window_end)})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1


@pytest.mark.django_db
class TestUpdateAndCancel:
    def test_owner_can_reschedule(self, api_client, visitor):
        start, end = slot()
        visit = Visit.objects.create(user=visitor, user_name=visitor.name, start=start, end=end)

        api_client.force_authenticate(user=visitor)
        new_start, new_end = slot(hours_from_now=3)
        response = api_client.patch(
            visit_url(visit.id), {"start": iso(new_start), "end": iso(new_end)}, format="json"
        )
        assert response.status_code == 200
        visit.refresh_from_db()
        assert visit.start == new_start

    def test_other_visitor_cannot_edit_someone_elses_booking(self, api_client, visitor, other_visitor):
        start, end = slot()
        visit = Visit.objects.create(user=visitor, user_name=visitor.name, start=start, end=end)

        api_client.force_authenticate(user=other_visitor)
        new_start, new_end = slot(hours_from_now=3)
        response = api_client.patch(
            visit_url(visit.id), {"start": iso(new_start), "end": iso(new_end)}, format="json"
        )
        assert response.status_code == 403

    def test_family_can_reschedule_anyones_booking(self, api_client, visitor, family_user):
        start, end = slot()
        visit = Visit.objects.create(user=visitor, user_name=visitor.name, start=start, end=end)

        api_client.force_authenticate(user=family_user)
        new_start, new_end = slot(hours_from_now=3)
        response = api_client.patch(
            visit_url(visit.id), {"start": iso(new_start), "end": iso(new_end)}, format="json"
        )
        assert response.status_code == 200

    def test_owner_can_cancel(self, api_client, visitor):
        start, end = slot()
        visit = Visit.objects.create(user=visitor, user_name=visitor.name, start=start, end=end)

        api_client.force_authenticate(user=visitor)
        response = api_client.post(cancel_url(visit.id))
        assert response.status_code == 200
        visit.refresh_from_db()
        assert visit.status == VisitStatus.CANCELLED
        assert visit.cancelled_at is not None

    def test_other_visitor_cannot_cancel_someone_elses_booking(self, api_client, visitor, other_visitor):
        start, end = slot()
        visit = Visit.objects.create(user=visitor, user_name=visitor.name, start=start, end=end)

        api_client.force_authenticate(user=other_visitor)
        response = api_client.post(cancel_url(visit.id))
        assert response.status_code == 403

    def test_family_can_cancel_anyones_booking(self, api_client, visitor, family_user):
        start, end = slot()
        visit = Visit.objects.create(user=visitor, user_name=visitor.name, start=start, end=end)

        api_client.force_authenticate(user=family_user)
        response = api_client.post(cancel_url(visit.id))
        assert response.status_code == 200

    def test_cancelling_twice_is_rejected(self, api_client, visitor):
        start, end = slot()
        visit = Visit.objects.create(
            user=visitor,
            user_name=visitor.name,
            start=start,
            end=end,
            status=VisitStatus.CANCELLED,
            cancelled_at=timezone.now(),
        )

        api_client.force_authenticate(user=visitor)
        response = api_client.post(cancel_url(visit.id))
        assert response.status_code == 400

    def test_cancelled_booking_cannot_be_edited(self, api_client, visitor):
        start, end = slot()
        visit = Visit.objects.create(
            user=visitor,
            user_name=visitor.name,
            start=start,
            end=end,
            status=VisitStatus.CANCELLED,
            cancelled_at=timezone.now(),
        )

        api_client.force_authenticate(user=visitor)
        new_start, new_end = slot(hours_from_now=3)
        response = api_client.patch(
            visit_url(visit.id), {"start": iso(new_start), "end": iso(new_end)}, format="json"
        )
        assert response.status_code == 400

    def test_visitor_cannot_turn_their_booking_into_a_block(self, api_client, visitor):
        start, end = slot()
        visit = Visit.objects.create(user=visitor, user_name=visitor.name, start=start, end=end)

        api_client.force_authenticate(user=visitor)
        response = api_client.patch(visit_url(visit.id), {"kind": "blocked"}, format="json")
        assert response.status_code == 403
