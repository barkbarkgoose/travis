"""Users app models."""

import secrets

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone

from apps.organizations.models import Organization


class UserManager(BaseUserManager):
    """Custom manager for User model."""

    def create_user(
        self, email, name, password=None, organization=None, **extra_fields
    ):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(
            email=email, name=name, organization=organization, **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email, name, password=None, organization=None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.FAMILY)
        if organization is None:
            organization = Organization.objects.create(name=f"Superuser Org ({email})")
        return self.create_user(email, name, password, organization, **extra_fields)


def default_user_settings() -> dict:
    """Default schema for per-user UI preferences."""
    return {
        "theme_colors": {},
        "default_view": "all",
    }


class Role(models.TextChoices):
    """Access level within the single family organization."""

    VISITOR = "visitor", "Visitor"
    FAMILY = "family", "Family"


class User(AbstractBaseUser, PermissionsMixin):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    # Authorization lives in a real column, never in `settings` (see below).
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VISITOR)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # --------------------------------------------------------------------------
    # SECURITY CONSIDERATIONS (User Settings JSONField):
    # 1. Scope Restriction: This field is strictly reserved for non-sensitive UI/UX
    #    preferences and encrypted credentials (e.g. theme colors, AI providers).
    # 2. Privilege Separation: NEVER store authorization flags (is_staff, is_superuser,
    #    roles), permissions, passwords, or security-critical state in this dictionary.
    # 3. Input Sanitization: All incoming updates MUST be validated and whitelisted at
    #    the serializer layer (UserSettingsSerializer) to prevent injection of
    #    unexpected keys, payload bloat (DoS), or untrusted HTML/scripts.
    # 4. Encryption: Secret values (e.g. api_keys) are encrypted at rest via
    #    apps.users.crypto before being persisted.
    # --------------------------------------------------------------------------
    settings = models.JSONField(
        default=default_user_settings,
        blank=True,
        help_text="User UI/UX preferences and encrypted per-user credentials.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_family(self) -> bool:
        """Family accounts (and superusers) can see and manage everything."""
        return self.is_active and (self.role == Role.FAMILY or self.is_superuser)


def new_invite_token() -> str:
    return secrets.token_urlsafe(32)


class Invite(models.Model):
    """A shareable join link. Rotating it revokes every earlier link.

    The token is stored in plain text so a family admin can re-display the link.
    It only grants the ability to join as a visitor, which is why visitors get
    their own identity (and can be revoked one by one).
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invites"
    )
    token = models.CharField(max_length=64, unique=True, default=new_invite_token)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])
