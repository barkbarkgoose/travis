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


def _join_payload(token, **overrides):
    payload = {
        "token": token,
        "full_name": "Maria Lopez",
        "email": "maria@example.com",
        "password": VALID_PASSWORD,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestJoin:
    def test_join_creates_visitor_and_returns_tokens(self, api_client, invite):
        response = api_client.post(
            "/api/v1/auth/join/",
            _join_payload(invite.token, full_name="  Maria   Lopez ", email="Maria@Example.com"),
            format="json",
        )
        assert response.status_code == 201
        assert "access" in response.data and "refresh" in response.data
        assert response.data["user"]["name"] == "Maria Lopez"
        assert response.data["user"]["role"] == "visitor"
        assert response.data["user"]["has_password"] is True
        assert response.data["user"]["needs_passkey"] is False

        user = User.objects.get(pk=response.data["user"]["id"])
        assert user.organization == invite.organization
        assert user.check_password(VALID_PASSWORD)
        assert not user.is_family

    def test_access_token_works(self, api_client, invite):
        response = api_client.post(
            "/api/v1/auth/join/", _join_payload(invite.token), format="json"
        )
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        assert api_client.get("/api/v1/auth/settings/").status_code == 200

    def test_joined_visitor_can_sign_in_on_another_device(self, api_client, invite):
        api_client.post("/api/v1/auth/join/", _join_payload(invite.token), format="json")
        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": "MARIA@example.com", "password": VALID_PASSWORD},
            format="json",
        )
        assert response.status_code == 200
        assert User.objects.filter(name="Maria Lopez").count() == 1

    def test_email_already_used_is_rejected(self, api_client, invite):
        api_client.post("/api/v1/auth/join/", _join_payload(invite.token), format="json")
        response = api_client.post(
            "/api/v1/auth/join/",
            _join_payload(invite.token, email="maria@EXAMPLE.com"),
            format="json",
        )
        assert response.status_code == 400
        assert "email" in response.data

    def test_weak_password_is_rejected(self, api_client, invite):
        response = api_client.post(
            "/api/v1/auth/join/", _join_payload(invite.token, password="password"), format="json"
        )
        assert response.status_code == 400
        assert "password" in response.data
        assert not User.objects.filter(email="maria@example.com").exists()

    def test_full_name_requires_first_and_last(self, api_client, invite):
        response = api_client.post(
            "/api/v1/auth/join/",
            _join_payload(invite.token, full_name="Maria"),
            format="json",
        )
        assert response.status_code == 400
        assert "full_name" in response.data

    def test_unknown_and_revoked_tokens_look_identical(self, api_client, invite):
        unknown = api_client.post(
            "/api/v1/auth/join/", _join_payload("nope"), format="json"
        )
        invite.revoke()
        revoked = api_client.post(
            "/api/v1/auth/join/", _join_payload(invite.token), format="json"
        )
        assert unknown.status_code == revoked.status_code == 400
        assert unknown.data == revoked.data
        assert not User.objects.filter(email="maria@example.com").exists()

    def test_join_is_throttled(self, api_client, monkeypatch):
        monkeypatch.setattr(JoinThrottle, "THROTTLE_RATES", {"join": "3/min"})
        codes = [
            api_client.post(
                "/api/v1/auth/join/",
                _join_payload("guess"),
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
            "/api/v1/auth/join/", _join_payload(invite.token), format="json"
        )
        new = api_client.post(
            "/api/v1/auth/join/", _join_payload(response.data["token"]), format="json"
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


# --- passkeys -----------------------------------------------------------------
# The browser side of WebAuthn can't run here, so the views are tested with the
# verify step (apps.users.passkeys.authenticate/register) swapped for a stub.

from rest_framework.exceptions import ValidationError as DRFValidationError  # noqa: E402

from apps.users import passkeys as passkey_module  # noqa: E402
from apps.users.models import Passkey  # noqa: E402

CEREMONY = {"state": "s", "credential": {"id": "x"}}


def _make_passkey(user, credential_id="cred-1"):
    return Passkey.objects.create(user=user, credential_id=credential_id, public_key=b"k")


def _bearer(client, access):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")


def _passkey_login(client, monkeypatch, passkey):
    monkeypatch.setattr(passkey_module, "authenticate", lambda state, credential: passkey)
    response = client.post("/api/v1/auth/passkeys/login/", CEREMONY, format="json")
    assert response.status_code == 200
    _bearer(client, response.data["access"])
    return response


@pytest.mark.django_db
class TestFamilyPasskeyRequirement:
    def test_password_session_without_passkey_has_no_family_powers(
        self, api_client, family_user, invite
    ):
        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": family_user.email, "password": VALID_PASSWORD},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["user"]["needs_passkey"] is True
        _bearer(api_client, response.data["access"])
        assert api_client.get("/api/v1/auth/invite/").status_code == 403

    def test_password_refused_once_family_has_passkey(self, api_client, family_user):
        _make_passkey(family_user)
        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": family_user.email, "password": VALID_PASSWORD},
            format="json",
        )
        assert response.status_code == 403
        assert response.data["code"] == "passkey_required"

    def test_wrong_password_does_not_reveal_passkey_requirement(self, api_client, family_user):
        _make_passkey(family_user)
        response = api_client.post(
            "/api/v1/auth/login/",
            {"email": family_user.email, "password": "wrong"},
            format="json",
        )
        assert response.status_code == 401

    def test_passkey_login_unlocks_family(self, api_client, monkeypatch, family_user, invite):
        response = _passkey_login(api_client, monkeypatch, _make_passkey(family_user))
        assert response.data["user"]["needs_passkey"] is False
        assert api_client.get("/api/v1/auth/invite/").status_code == 200

    def test_refresh_keeps_passkey_session(self, api_client, monkeypatch, family_user, invite):
        login = _passkey_login(api_client, monkeypatch, _make_passkey(family_user))
        api_client.credentials()
        refreshed = api_client.post(
            "/api/v1/auth/refresh/", {"refresh": login.data["refresh"]}, format="json"
        )
        _bearer(api_client, refreshed.data["access"])
        assert api_client.get("/api/v1/auth/invite/").status_code == 200

    def test_registering_first_passkey_unlocks_family(
        self, api_client, monkeypatch, family_user, invite
    ):
        login = api_client.post(
            "/api/v1/auth/login/",
            {"email": family_user.email, "password": VALID_PASSWORD},
            format="json",
        )
        _bearer(api_client, login.data["access"])
        monkeypatch.setattr(
            passkey_module,
            "register",
            lambda user, state, credential, name="": _make_passkey(user),
        )
        response = api_client.post("/api/v1/auth/passkeys/", CEREMONY, format="json")
        assert response.status_code == 201
        assert response.data["user"]["passkey_count"] == 1
        _bearer(api_client, response.data["access"])
        assert api_client.get("/api/v1/auth/invite/").status_code == 200

    def test_cannot_delete_last_family_passkey(self, api_client, monkeypatch, family_user):
        passkey = _make_passkey(family_user)
        _passkey_login(api_client, monkeypatch, passkey)
        response = api_client.delete(f"/api/v1/auth/passkeys/{passkey.pk}/")
        assert response.status_code == 400
        assert Passkey.objects.filter(pk=passkey.pk).exists()


@pytest.mark.django_db
class TestVisitorPasskeys:
    def test_password_session_cannot_add_passkey_when_one_exists(
        self, api_client, sample_user
    ):
        _make_passkey(sample_user)
        login = api_client.post(
            "/api/v1/auth/login/",
            {"email": sample_user.email, "password": VALID_PASSWORD},
            format="json",
        )
        assert login.status_code == 200  # passkeys are optional for visitors
        _bearer(api_client, login.data["access"])
        response = api_client.post("/api/v1/auth/passkeys/register/options/")
        assert response.status_code == 400
        assert response.data["code"] == "passkey_required"

    def test_register_options_for_first_passkey(self, api_client, sample_user):
        api_client.force_authenticate(user=sample_user)
        response = api_client.post("/api/v1/auth/passkeys/register/options/")
        assert response.status_code == 200
        assert response.data["options"]["rp"]["id"] == "localhost"
        assert response.data["state"]

    def test_visitor_can_delete_their_only_passkey(self, api_client, monkeypatch, sample_user):
        passkey = _make_passkey(sample_user)
        _passkey_login(api_client, monkeypatch, passkey)
        assert api_client.delete(f"/api/v1/auth/passkeys/{passkey.pk}/").status_code == 204

    def test_cannot_delete_someone_elses_passkey(self, api_client, monkeypatch, sample_user, family_user):
        theirs = _make_passkey(family_user, "cred-theirs")
        _passkey_login(api_client, monkeypatch, _make_passkey(sample_user))
        assert api_client.delete(f"/api/v1/auth/passkeys/{theirs.pk}/").status_code == 404

    def test_list_passkeys(self, api_client, sample_user):
        _make_passkey(sample_user)
        api_client.force_authenticate(user=sample_user)
        response = api_client.get("/api/v1/auth/passkeys/")
        assert [p["id"] for p in response.data] == [sample_user.passkeys.get().pk]


@pytest.mark.django_db
class TestChangePassword:
    NEW = "AnotherGoodPass456!"

    def test_change_with_own_passkey(self, api_client, monkeypatch, sample_user):
        passkey = _make_passkey(sample_user)
        api_client.force_authenticate(user=sample_user)
        monkeypatch.setattr(passkey_module, "authenticate", lambda state, credential: passkey)
        response = api_client.post(
            "/api/v1/auth/password/", {**CEREMONY, "new_password": self.NEW}, format="json"
        )
        assert response.status_code == 200
        sample_user.refresh_from_db()
        assert sample_user.check_password(self.NEW)

    def test_someone_elses_passkey_is_refused(
        self, api_client, monkeypatch, sample_user, family_user
    ):
        theirs = _make_passkey(family_user)
        api_client.force_authenticate(user=sample_user)
        monkeypatch.setattr(passkey_module, "authenticate", lambda state, credential: theirs)
        response = api_client.post(
            "/api/v1/auth/password/", {**CEREMONY, "new_password": self.NEW}, format="json"
        )
        assert response.status_code == 400
        sample_user.refresh_from_db()
        assert sample_user.check_password(VALID_PASSWORD)

    def test_failed_passkey_check_is_refused(self, api_client, monkeypatch, sample_user):
        def fail(state, credential):
            raise DRFValidationError({"detail": passkey_module.INVALID})

        api_client.force_authenticate(user=sample_user)
        monkeypatch.setattr(passkey_module, "authenticate", fail)
        response = api_client.post(
            "/api/v1/auth/password/", {**CEREMONY, "new_password": self.NEW}, format="json"
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestClaimAccount:
    def test_legacy_visitor_adds_email_and_password(self, api_client, invite):
        legacy = User.objects.create_user(
            email="visitor-abc@visitors.invalid", name="Old Visitor", organization=invite.organization
        )
        assert not legacy.has_usable_password()
        api_client.force_authenticate(user=legacy)
        response = api_client.post(
            "/api/v1/auth/account/",
            {"email": "old@example.com", "password": VALID_PASSWORD},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["has_password"] is True
        legacy.refresh_from_db()
        assert legacy.email == "old@example.com" and legacy.check_password(VALID_PASSWORD)

        again = api_client.post(
            "/api/v1/auth/account/",
            {"email": "new@example.com", "password": VALID_PASSWORD},
            format="json",
        )
        assert again.status_code == 400


@pytest.mark.django_db
class TestAdminAccess:
    def test_admin_password_form_redirects_to_app(self, client):
        response = client.get("/admin/login/")
        assert response.status_code == 302
        assert response["Location"] == "/admin-signin"

    def test_admin_session_needs_passkey(self, api_client, family_user):
        family_user.is_staff = True
        family_user.save(update_fields=["is_staff"])
        login = api_client.post(
            "/api/v1/auth/login/",
            {"email": family_user.email, "password": VALID_PASSWORD},
            format="json",
        )
        _bearer(api_client, login.data["access"])
        assert api_client.post("/api/v1/auth/admin-session/").status_code == 403

    def test_admin_session_with_passkey(self, api_client, monkeypatch, family_user):
        family_user.is_staff = True
        family_user.save(update_fields=["is_staff"])
        _passkey_login(api_client, monkeypatch, _make_passkey(family_user))
        response = api_client.post("/api/v1/auth/admin-session/")
        assert response.status_code == 204
        assert api_client.get("/admin/").status_code == 200


class TestPasskeyState:
    def test_tampered_state_is_rejected(self):
        with pytest.raises(DRFValidationError):
            passkey_module.authenticate("not-a-signed-state", {"id": "x"})

    def test_state_from_another_ceremony_is_rejected(self):
        register_state = passkey_module._sign_state("register", b"challenge", 1)
        with pytest.raises(DRFValidationError):
            passkey_module.authenticate(register_state, {"id": "x"})

    @pytest.mark.django_db
    def test_register_state_is_bound_to_the_user(self, sample_user, family_user):
        state = passkey_module._sign_state("register", b"challenge", family_user.pk)
        with pytest.raises(DRFValidationError):
            passkey_module.register(sample_user, state, {"id": "x"})

    @pytest.mark.django_db
    def test_unknown_credential_is_rejected(self):
        state = passkey_module._sign_state("authenticate", b"challenge", None)
        with pytest.raises(DRFValidationError):
            passkey_module.authenticate(state, {"id": "nobody"})


# --- real WebAuthn round trip ---------------------------------------------------
# A tiny software authenticator (P-256, "none" attestation) so the actual
# signature and challenge checks in apps.users.passkeys run end to end.

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402

import cbor2  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from django.conf import settings as dj_settings  # noqa: E402
from webauthn.helpers import bytes_to_base64url  # noqa: E402


class SoftAuthenticator:
    FLAGS_UP_UV = 0x01 | 0x04

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.counter = 0
        self.origin = dj_settings.WEBAUTHN_ORIGINS[0]
        self.rp_hash = hashlib.sha256(dj_settings.WEBAUTHN_RP_ID.encode()).digest()

    def _client_data(self, kind, challenge):
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}
        ).encode()

    def create(self, options):
        numbers = self.key.public_key().public_numbers()
        cose_key = cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")}
        )
        auth_data = (
            self.rp_hash
            + bytes([self.FLAGS_UP_UV | 0x40])
            + self.counter.to_bytes(4, "big")
            + bytes(16)
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + cose_key
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cid = bytes_to_base64url(self.credential_id)
        return {
            "id": cid,
            "rawId": cid,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(
                    self._client_data("webauthn.create", options["challenge"])
                ),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def get(self, options, user_id):
        self.counter += 1
        auth_data = self.rp_hash + bytes([self.FLAGS_UP_UV]) + self.counter.to_bytes(4, "big")
        client_data = self._client_data("webauthn.get", options["challenge"])
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        cid = bytes_to_base64url(self.credential_id)
        return {
            "id": cid,
            "rawId": cid,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(str(user_id).encode()),
            },
            "clientExtensionResults": {},
        }


@pytest.mark.django_db
def test_real_passkey_register_and_sign_in(api_client, family_user, invite):
    device = SoftAuthenticator()

    # First sign-in with the password: limited session, can only add a passkey.
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": family_user.email, "password": VALID_PASSWORD},
        format="json",
    )
    _bearer(api_client, login.data["access"])
    ceremony = api_client.post("/api/v1/auth/passkeys/register/options/").data
    assert ceremony["options"]["authenticatorSelection"]["residentKey"] == "required"
    saved = api_client.post(
        "/api/v1/auth/passkeys/",
        {"state": ceremony["state"], "credential": device.create(ceremony["options"]), "name": "Laptop"},
        format="json",
    )
    assert saved.status_code == 201, saved.data
    assert saved.data["passkey"]["name"] == "Laptop"

    # New device: sign in with the passkey alone.
    api_client.credentials()
    ceremony = api_client.post("/api/v1/auth/passkeys/auth/options/").data
    assertion = device.get(ceremony["options"], family_user.pk)
    signed_in = api_client.post(
        "/api/v1/auth/passkeys/login/",
        {"state": ceremony["state"], "credential": assertion},
        format="json",
    )
    assert signed_in.status_code == 200, signed_in.data
    _bearer(api_client, signed_in.data["access"])
    assert api_client.get("/api/v1/auth/invite/").status_code == 200

    # Replaying the same assertion fails: the sign counter has moved on.
    replay = api_client.post(
        "/api/v1/auth/passkeys/login/",
        {"state": ceremony["state"], "credential": assertion},
        format="json",
    )
    assert replay.status_code == 400

    # A challenge the server didn't issue is rejected.
    forged = device.get({"challenge": bytes_to_base64url(b"not-the-challenge")}, family_user.pk)
    rejected = api_client.post(
        "/api/v1/auth/passkeys/login/",
        {"state": ceremony["state"], "credential": forged},
        format="json",
    )
    assert rejected.status_code == 400
