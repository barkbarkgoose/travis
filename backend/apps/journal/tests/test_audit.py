"""The family-only audit trail endpoint."""

import pytest

from apps.journal.audit import log_audit
from apps.journal.models import AuditAction, Entry

AUDIT_URL = "/api/v1/journal/audit/"


@pytest.mark.django_db
class TestAuditList:
    def test_visitor_forbidden(self, api_client, visitor):
        api_client.force_authenticate(user=visitor)
        assert api_client.get(AUDIT_URL).status_code == 403

    def test_unauthenticated_is_401(self, api_client):
        assert api_client.get(AUDIT_URL).status_code == 401

    def test_family_sees_events_scoped_to_their_org(
        self, api_client, family_user, visitor, other_org_visitor
    ):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        other_entry = Entry.objects.create(
            author=other_org_visitor, author_name=other_org_visitor.name
        )
        log_audit(actor=visitor, action=AuditAction.ENTRY_SUBMITTED, obj=entry)
        log_audit(actor=other_org_visitor, action=AuditAction.ENTRY_SUBMITTED, obj=other_entry)

        api_client.force_authenticate(user=family_user)
        response = api_client.get(AUDIT_URL)

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["actor_name"] == visitor.name

    def test_events_are_newest_first(self, api_client, family_user, visitor):
        entry = Entry.objects.create(author=visitor, author_name=visitor.name)
        first = log_audit(actor=visitor, action=AuditAction.ENTRY_SUBMITTED, obj=entry)
        second = log_audit(actor=visitor, action=AuditAction.ENTRY_EDITED, obj=entry)

        api_client.force_authenticate(user=family_user)
        response = api_client.get(AUDIT_URL)

        ids = [row["id"] for row in response.data["results"]]
        assert ids.index(second.id) < ids.index(first.id)
