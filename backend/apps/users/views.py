"""Users app views."""

import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Invite, Role
from .permissions import IsFamily
from .serializers import (
    JoinSerializer,
    LoginSerializer,
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


def _token_payload(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user).data,
    }


class JoinView(APIView):
    """Create a visitor identity from a shared invite link and sign them in.

    Visitors have no password. Each gets their own account so that entries and
    photos are attributed to a named person and a single visitor can be revoked
    without rotating the link for everyone.
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

        with transaction.atomic():
            user = User(
                organization=invite.organization,
                email=f"visitor-{uuid.uuid4().hex}@visitors.invalid",
                name=serializer.validated_data["full_name"],
                role=Role.VISITOR,
            )
            user.set_unusable_password()
            user.save()

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
    """Authenticate user and return JWT tokens plus the user payload."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        try:
            user = User.objects.get(email=email)
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
        return Response(
            {"access": str(new_refresh.access_token), "refresh": str(new_refresh)},
            status=status.HTTP_200_OK,
        )
