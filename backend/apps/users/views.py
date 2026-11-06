"""Users app views."""

from django.contrib.auth import get_user_model
from django.contrib.auth import login as session_login
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from . import passkeys
from .authentication import PASSKEY_CLAIM, PASSKEY_VALUE
from .models import Invite, Role
from .permissions import IsFamily
from .serializers import (
    ChangePasswordSerializer,
    ClaimAccountSerializer,
    JoinSerializer,
    LoginSerializer,
    PasskeyCeremonySerializer,
    PasskeyRegisterSerializer,
    PasskeySerializer,
    UserSerializer,
    UserSettingsSerializer,
    format_safe_user_settings,
)

User = get_user_model()


class UserSettingsView(APIView):
    """
    Retrieve and update the authenticated user's UI settings.

    --------------------------------------------------------------------------
    SECURITY CONSIDERATIONS:
    1. Authentication & Ownership Isolation: Requires an authenticated session
       or JWT. Users can ONLY inspect and modify their own settings object,
       preventing cross-tenant / horizontal privilege escalation.
    2. Partial Merging with Strict Validation: Updates are validated through
       UserSettingsSerializer. Unauthorized keys are stripped.
    3. Key Masking on Read: Stored API keys are masked before serialization.
    --------------------------------------------------------------------------
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(format_safe_user_settings(request.user.settings or {}))

    def patch(self, request):
        serializer = UserSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        current_settings = request.user.settings or {}
        incoming = serializer.validated_data

        # Merge nested api_keys if provided so providers are updated individually.
        if "api_keys" in incoming and isinstance(current_settings.get("api_keys"), dict):
            incoming["api_keys"] = {**current_settings["api_keys"], **incoming["api_keys"]}

        request.user.settings = {**current_settings, **incoming}
        request.user.save(update_fields=["settings"])

        return Response(
            format_safe_user_settings(request.user.settings),
            status=status.HTTP_200_OK,
        )


class JoinThrottle(AnonRateThrottle):
    """Slow down guessing of invite tokens (rate set in REST_FRAMEWORK)."""

    scope = "join"


class LoginThrottle(AnonRateThrottle):
    """Slow down password and passkey guessing (rate set in REST_FRAMEWORK)."""

    scope = "login"


def _token_payload(user, *, passkey: bool = False) -> dict:
    """Tokens plus the user. `passkey` marks the session as opened with a passkey,
    which family powers require (see apps.users.authentication)."""
    refresh = RefreshToken.for_user(user)
    if passkey:
        refresh[PASSKEY_CLAIM] = PASSKEY_VALUE
    user.passkey_session = passkey
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user).data,
    }


class JoinView(APIView):
    """Create a visitor account from a shared invite link and sign them in.

    This is the only way to create an account from outside: there is no open
    sign-up. The email and password let the same person sign in on other devices.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [JoinThrottle]

    def post(self, request):
        serializer = JoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # One generic error for unknown and revoked tokens, so a guesser learns
        # nothing about which tokens ever existed.
        invalid = Response(
            {"detail": "This invite link isn't valid. Ask the family for a new one."},
            status=status.HTTP_400_BAD_REQUEST,
        )
        try:
            invite = Invite.objects.select_related("organization").get(
                token=serializer.validated_data["token"]
            )
        except Invite.DoesNotExist:
            return invalid
        if not invite.is_active:
            return invalid

        data = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                name=data["full_name"],
                password=data["password"],
                organization=invite.organization,
                role=Role.VISITOR,
            )

        return Response(_token_payload(user), status=status.HTTP_201_CREATED)


class InviteView(APIView):
    """Family-only: show the current invite link, or rotate it."""

    permission_classes = [IsFamily]

    @staticmethod
    def _current(organization):
        return organization.invites.filter(revoked_at__isnull=True).first()

    def get(self, request):
        invite = self._current(request.user.organization)
        return Response({"token": invite.token if invite else None})

    def post(self, request):
        """Revoke every active link and issue a new one."""
        organization = request.user.organization
        with transaction.atomic():
            for old in organization.invites.filter(revoked_at__isnull=True):
                old.revoke()
            invite = Invite.objects.create(
                organization=organization, created_by=request.user
            )
        return Response({"token": invite.token}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """Authenticate user and return JWT tokens plus the user payload.

    Family accounts that have a passkey must use it; the password alone is
    refused. A family account without one gets a limited session whose only use
    is adding a passkey.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.check_password(password):
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"detail": "User account is disabled."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user.has_family_role and user.passkeys.exists():
            return Response(
                {
                    "detail": "Family accounts sign in with a passkey.",
                    "code": "passkey_required",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(_token_payload(user), status=status.HTTP_200_OK)


class RefreshTokenView(APIView):
    """Refresh access token using refresh token."""

    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_token)
            user = User.objects.get(pk=refresh["user_id"])
        except Exception:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # A revoked or deactivated user must not be able to keep a session alive.
        if not user.is_active:
            return Response(
                {"detail": "User account is disabled."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Sliding session: each refresh issues a fresh refresh token, so someone
        # who keeps visiting is not asked to rejoin every few weeks.
        new_refresh = RefreshToken.for_user(user)
        if refresh.get(PASSKEY_CLAIM) == PASSKEY_VALUE:
            new_refresh[PASSKEY_CLAIM] = PASSKEY_VALUE
        return Response(
            {"access": str(new_refresh.access_token), "refresh": str(new_refresh)},
            status=status.HTTP_200_OK,
        )


def _require_passkey_session(request) -> None:
    """Changing sign-in methods on an account that has a passkey needs a passkey session,
    so a leaked password can't be used to add an attacker's passkey or swap the password."""
    if request.user.passkeys.exists() and not getattr(
        request.user, "passkey_session", False
    ):
        raise ValidationError(
            {"detail": "Sign in with your passkey first.", "code": "passkey_required"}
        )


class PasskeyAuthOptionsView(APIView):
    """Start a passkey prompt. Signed-in users get one limited to their own passkeys."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        user = request.user if request.user.is_authenticated else None
        return Response(passkeys.authentication_options(user))


class PasskeyLoginView(APIView):
    """Sign in with a passkey. No email needed: the passkey identifies the account."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = PasskeyCeremonySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        passkey = passkeys.authenticate(**serializer.validated_data)
        if not passkey.user.is_active:
            return Response(
                {"detail": "User account is disabled."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(_token_payload(passkey.user, passkey=True))


class PasskeyRegisterOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        _require_passkey_session(request)
        return Response(passkeys.registration_options(request.user))


class PasskeyListView(APIView):
    """List the user's passkeys (GET) or save a new one (POST).

    Saving a passkey returns fresh tokens marked as a passkey session: the
    browser just checked the user's face, fingerprint or PIN to create it.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(PasskeySerializer(request.user.passkeys.all(), many=True).data)

    def post(self, request):
        _require_passkey_session(request)
        serializer = PasskeyRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        passkey = passkeys.register(request.user, **serializer.validated_data)
        return Response(
            {
                "passkey": PasskeySerializer(passkey).data,
                **_token_payload(request.user, passkey=True),
            },
            status=status.HTTP_201_CREATED,
        )


class PasskeyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        passkey = get_object_or_404(request.user.passkeys, pk=pk)
        _require_passkey_session(request)
        if request.user.has_family_role and request.user.passkeys.count() == 1:
            return Response(
                {"detail": "Family accounts need at least one passkey. Add another first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        passkey.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    """Change your own password, confirmed with one of your passkeys.

    Without a passkey there's no self-service change: a family admin resets the
    password in the Django admin instead.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        passkey = passkeys.authenticate(data["state"], data["credential"])
        if passkey.user_id != request.user.id:
            raise ValidationError({"detail": passkeys.INVALID})
        request.user.set_password(data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password changed."})


class ClaimAccountView(APIView):
    """Give an email and password to a visitor who joined before passwords existed.

    Only works once, for accounts with no usable password.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.has_usable_password():
            return Response(
                {"detail": "This account already has a password."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ClaimAccountSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user.email = serializer.validated_data["email"]
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["email", "password"])
        return Response(UserSerializer(user).data)


class AdminSessionView(APIView):
    """Open a Django admin session for staff who signed in with a passkey.

    The admin's own password form is switched off (see admin.py), so this is
    the only way in.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not (user.is_staff and getattr(user, "passkey_session", False)):
            return Response(
                {
                    "detail": "The admin needs a staff account signed in with a passkey.",
                    "code": "passkey_required",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        session_login(
            request._request, user, backend="django.contrib.auth.backends.ModelBackend"
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
