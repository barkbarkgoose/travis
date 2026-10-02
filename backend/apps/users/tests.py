"""Tests for the users app: auth payload and UserSettingsView."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.organizations.models import Organization

User = get_user_model()

VALID_PASSWORD = "ValidPassword123!"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_user():
    org = Organization.objects.create(name="Test Org")
    return User.objects.create_user(
        email="test@example.com",
        name="Test User",
        password=VALID_PASSWORD,
        organization=org,
    )


@pytest.mark.django_db
class TestAuthViews:
    def test_login_returns_user_payload(self, api_client, sample_user):
        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": sample_user.email, "password": VALID_PASSWORD},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data
        # Regression guard: the frontend needs the user payload on login,
        # otherwise it stays logged in with a null user.
        assert response.data["user"]["email"] == sample_user.email


@pytest.mark.django_db
class TestUserSettingsAPI:
    def test_settings_unauthenticated(self, api_client):
        response = api_client.get("/api/v1/auth/settings/")
        assert response.status_code == 401

    def test_get_settings_authenticated(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        response = api_client.get("/api/v1/auth/settings/")
        assert response.status_code == 200
        assert "theme_colors" in response.data

    def test_update_settings_valid(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        payload = {
            "theme_colors": {
                "primary": "#8b5cf6",
                "accent": "emerald",
            },
            "default_view": "upcoming",
        }
        response = api_client.patch("/api/v1/auth/settings/", payload, format="json")
        assert response.status_code == 200
        assert response.data["theme_colors"]["primary"] == "#8b5cf6"
        assert response.data["theme_colors"]["accent"] == "emerald"
        assert response.data["default_view"] == "upcoming"

        sample_user.refresh_from_db()
        assert sample_user.settings["theme_colors"]["primary"] == "#8b5cf6"

    def test_update_settings_strips_disallowed_keys(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        payload = {
            "theme_colors": {"primary": "#10b981"},
            "is_staff": True,  # Disallowed / dangerous key
            "is_superuser": True,
            "role": "admin",
        }
        response = api_client.patch("/api/v1/auth/settings/", payload, format="json")
        assert response.status_code == 200
        sample_user.refresh_from_db()
        assert not sample_user.is_staff
        assert not sample_user.is_superuser
        assert "is_staff" not in sample_user.settings
        assert "role" not in sample_user.settings

    def test_update_settings_invalid_color_rejected(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        payload = {"theme_colors": {"primary": "javascript:alert(1);"}}
        response = api_client.patch("/api/v1/auth/settings/", payload, format="json")
        assert response.status_code == 400
        assert "theme_colors" in response.data

    def test_api_keys_are_encrypted_at_rest_in_db(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        raw_key = "AIzaSyDummySecretKeyForTesting12345"
        payload = {
            "api_keys": {
                "google": raw_key,
                "anthropic": "sk-ant-testkey67890",
            }
        }
        response = api_client.patch("/api/v1/auth/settings/", payload, format="json")
        assert response.status_code == 200

        # Safe response: raw key is never returned to the frontend.
        assert "api_keys" not in response.data
        status_info = response.data.get("api_keys_status", {})
        assert status_info["google"]["is_configured"] is True
        assert status_info["google"]["preview"].endswith("2345")
        assert raw_key not in status_info["google"]["preview"]

        # Database verification: the raw key is NOT plain text in SQLite.
        sample_user.refresh_from_db()
        stored_keys = sample_user.settings.get("api_keys", {})
        assert stored_keys["google"] != raw_key
        assert stored_keys["google"].startswith("gAAAAA")  # Fernet token

        from apps.users.crypto import decrypt_secret

        assert decrypt_secret(stored_keys["google"]) == raw_key
        assert decrypt_secret(stored_keys["anthropic"]) == "sk-ant-testkey67890"

    def test_api_key_can_be_removed(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        api_client.patch(
            "/api/v1/auth/settings/",
            {"api_keys": {"openai": "sk-test-key-123456"}},
            format="json",
        )

        response = api_client.patch(
            "/api/v1/auth/settings/",
            {"api_keys": {"openai": ""}},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["api_keys_status"]["openai"]["is_configured"] is False


# ---------------------------------------------------------------------------
# Invite / join flow
# ---------------------------------------------------------------------------

from io import StringIO  # noqa: E402

from django.core.cache import cache  # noqa: E402
from django.core.management import call_command  # noqa: E402
from rest_framework_simplejwt.tokens import RefreshToken  # noqa: E402

from apps.users.models import Invite, Role  # noqa: E402
from apps.users.views import JoinThrottle  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def family_org():
    return Organization.objects.create(name="Family")


@pytest.fixture
def invite(family_org):
    return Invite.objects.create(organization=family_org)


@pytest.fixture
def family_user(family_org):
    return User.objects.create_user(
        email="admin@example.com",
        name="Admin Person",
        password=VALID_PASSWORD,
        organization=family_org,
        role=Role.FAMILY,
    )


@pytest.mark.django_db
class TestJoin:
    def test_join_creates_visitor_and_returns_tokens(self, api_client, invite):
        response = api_client.post(
            "/api/v1/auth/join/",
            {"token": invite.token, "full_name": "  Maria   Lopez "},
            format="json",
        )
        assert response.status_code == 201
        assert "access" in response.data and "refresh" in response.data
        assert response.data["user"]["name"] == "Maria Lopez"
        assert response.data["user"]["role"] == "visitor"

        user = User.objects.get(pk=response.data["user"]["id"])
        assert user.organization == invite.organization
        assert user.email.endswith("@visitors.invalid")
        assert not user.has_usable_password()
        assert not user.is_family

    def test_access_token_works(self, api_client, invite):
        response = api_client.post(
            "/api/v1/auth/join/",
            {"token": invite.token, "full_name": "Maria Lopez"},
            format="json",
        )
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        assert api_client.get("/api/v1/auth/settings/").status_code == 200

    def test_two_joins_with_same_name_are_separate_identities(self, api_client, invite):
        payload = {"token": invite.token, "full_name": "Maria Lopez"}
        first = api_client.post("/api/v1/auth/join/", payload, format="json")
        second = api_client.post("/api/v1/auth/join/", payload, format="json")
        assert first.data["user"]["id"] != second.data["user"]["id"]

    def test_full_name_requires_first_and_last(self, api_client, invite):
        response = api_client.post(
            "/api/v1/auth/join/",
            {"token": invite.token, "full_name": "Maria"},
            format="json",
        )
        assert response.status_code == 400
        assert "full_name" in response.data

    def test_unknown_and_revoked_tokens_look_identical(self, api_client, invite):
        unknown = api_client.post(
            "/api/v1/auth/join/",
            {"token": "nope", "full_name": "Maria Lopez"},
            format="json",
        )
        invite.revoke()
        revoked = api_client.post(
            "/api/v1/auth/join/",
            {"token": invite.token, "full_name": "Maria Lopez"},
            format="json",
        )
        assert unknown.status_code == revoked.status_code == 400
        assert unknown.data == revoked.data
        assert User.objects.filter(email__endswith="@visitors.invalid").count() == 0

    def test_join_is_throttled(self, api_client, monkeypatch):
        monkeypatch.setattr(JoinThrottle, "THROTTLE_RATES", {"join": "3/min"})
        codes = [
            api_client.post(
                "/api/v1/auth/join/",
                {"token": "guess", "full_name": "Some One"},
                format="json",
            ).status_code
            for _ in range(5)
        ]
        assert codes[:3] == [400, 400, 400]
        assert 429 in codes[3:]

    def test_open_registration_is_gone(self, api_client):
        response = api_client.post(
            "/api/v1/auth/register/",
            {
                "email": "x@example.com",
                "password": VALID_PASSWORD,
                "name": "X",
                "organization_name": "X",
            },
            format="json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestInviteManagement:
    def test_visitor_cannot_see_or_rotate_invite(self, api_client, invite):
        visitor = User.objects.create_user(
            email="v@visitors.invalid",
            name="Vis Itor",
            organization=invite.organization,
        )
        api_client.force_authenticate(user=visitor)
        assert api_client.get("/api/v1/auth/invite/").status_code == 403
        assert api_client.post("/api/v1/auth/invite/").status_code == 403

    def test_anonymous_cannot_see_invite(self, api_client, invite):
        assert api_client.get("/api/v1/auth/invite/").status_code == 401

    def test_family_sees_current_invite(self, api_client, family_user, invite):
        api_client.force_authenticate(user=family_user)
        response = api_client.get("/api/v1/auth/invite/")
        assert response.status_code == 200
        assert response.data["token"] == invite.token

    def test_rotate_revokes_old_link(self, api_client, family_user, invite):
        api_client.force_authenticate(user=family_user)
        response = api_client.post("/api/v1/auth/invite/")
        assert response.status_code == 201
        assert response.data["token"] != invite.token

        api_client.force_authenticate(user=None)
        old = api_client.post(
            "/api/v1/auth/join/",
            {"token": invite.token, "full_name": "Maria Lopez"},
            format="json",
        )
        new = api_client.post(
            "/api/v1/auth/join/",
            {"token": response.data["token"], "full_name": "Maria Lopez"},
            format="json",
        )
        assert old.status_code == 400
        assert new.status_code == 201


@pytest.mark.django_db
class TestRefresh:
    def test_refresh_returns_new_pair(self, api_client, family_user):
        refresh = RefreshToken.for_user(family_user)
        response = api_client.post(
            "/api/v1/auth/refresh/", {"refresh": str(refresh)}, format="json"
        )
        assert response.status_code == 200
        assert response.data["access"] and response.data["refresh"]

    def test_revoked_user_cannot_refresh(self, api_client, family_user):
        refresh = RefreshToken.for_user(family_user)
        family_user.is_active = False
        family_user.save(update_fields=["is_active"])
        response = api_client.post(
            "/api/v1/auth/refresh/", {"refresh": str(refresh)}, format="json"
        )
        assert response.status_code == 401

    def test_access_token_is_not_accepted_as_refresh(self, api_client, family_user):
        access = str(RefreshToken.for_user(family_user).access_token)
        response = api_client.post(
            "/api/v1/auth/refresh/", {"refresh": access}, format="json"
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestBootstrapFamily:
    def test_creates_org_admin_and_invite_and_is_rerunnable(self):
        out = StringIO()
        args = ["--org-name", "Fam", "--admin", "Jake Barker <jake@example.com>"]
        call_command("bootstrap_family", *args, stdout=out)

        admin = User.objects.get(email="jake@example.com")
        assert admin.role == Role.FAMILY and admin.is_family and admin.is_staff
        assert admin.name == "Jake Barker"
        assert Invite.objects.filter(revoked_at__isnull=True).count() == 1
        assert "/join/" in out.getvalue()

        out2 = StringIO()
        call_command("bootstrap_family", *args, stdout=out2)
        assert User.objects.filter(email="jake@example.com").count() == 1
        assert Invite.objects.filter(revoked_at__isnull=True).count() == 1
        assert "already exists" in out2.getvalue()
        assert "password:" not in out2.getvalue()


@pytest.mark.django_db
def test_superuser_is_family():
    su = User.objects.create_superuser(email="su@example.com", name="Super User", password=VALID_PASSWORD)
    assert su.role == Role.FAMILY and su.is_family
