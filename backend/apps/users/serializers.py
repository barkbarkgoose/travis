"""Users app serializers."""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.organizations.models import Organization
from apps.users.crypto import decrypt_secret, encrypt_secret
from apps.users.models import Passkey

User = get_user_model()

# Whitelist of allowed root keys in user.settings to prevent untrusted payload pollution
ALLOWED_SETTINGS_KEYS = {
    "theme_colors",
    "default_view",
    "api_keys",
    "default_ai_provider",
}

# Safe color string pattern: hex color (#fff, #123456) or a simple color name
SAFE_COLOR_PATTERN = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z0-9_-]{1,30})$")
ALLOWED_API_KEY_PROVIDERS = {"anthropic", "google", "openai", "ollama"}


def mask_api_key(key: str) -> str:
    """Mask an API key for safe UI display (e.g. sk-ant-••••••••1234)."""
    if not key or len(key) < 8:
        return "••••••••"
    return f"{key[:6]}••••••••{key[-4:]}"


def format_safe_user_settings(settings: dict) -> dict:
    """Return user settings with masked API key metadata for safe serialization."""
    if not isinstance(settings, dict):
        return {}
    safe_copy = dict(settings)
    raw_keys = safe_copy.pop("api_keys", {})
    if isinstance(raw_keys, dict):
        masked_keys = {}
        for provider, value in raw_keys.items():
            if value:
                # Decrypt in memory only to generate the safe preview mask
                decrypted = decrypt_secret(str(value))
                masked_keys[provider] = {
                    "is_configured": True,
                    "preview": mask_api_key(decrypted),
                }
            else:
                masked_keys[provider] = {"is_configured": False, "preview": ""}
        safe_copy["api_keys_status"] = masked_keys
    return safe_copy


class UserSettingsSerializer(serializers.Serializer):
    """
    Serializer and sanitizer for the user settings JSON field.

    --------------------------------------------------------------------------
    SECURITY CONSIDERATIONS:
    1. Key Whitelisting: Unknown/unsupported keys are strictly stripped out to
       prevent arbitrary JSON bloat, prototype pollution patterns, or storage of
       unauthorized configuration.
    2. Input Validation: Dictionary entries validate bounded string lengths.
       API keys are limited to 255 chars and provider names must be in
       ALLOWED_API_KEY_PROVIDERS.
    3. Encryption: API keys are encrypted before they reach the database.
    --------------------------------------------------------------------------
    """

    theme_colors = serializers.DictField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=dict,
    )
    default_view = serializers.CharField(max_length=50, required=False, default="all")
    default_ai_provider = serializers.CharField(
        max_length=50, required=False, default="heuristic"
    )
    api_keys = serializers.DictField(
        child=serializers.CharField(max_length=255, allow_blank=True),
        required=False,
        default=dict,
    )

    def validate_theme_colors(self, value: dict) -> dict:
        if len(value) > 100:
            raise serializers.ValidationError("Too many color mappings (max 100).")
        sanitized = {}
        for item_key, color_value in value.items():
            clean_key = str(item_key)[:100].strip()
            clean_value = str(color_value).strip()
            if not SAFE_COLOR_PATTERN.match(clean_value):
                raise serializers.ValidationError(
                    f"Invalid color value for '{clean_key}'. Must be a hex code "
                    "(e.g. #8b5cf6) or a standard color name."
                )
            sanitized[clean_key] = clean_value
        return sanitized

    def validate_api_keys(self, value: dict) -> dict:
        sanitized = {}
        for provider_key, key_value in value.items():
            provider = str(provider_key).lower().strip()
            if provider in ALLOWED_API_KEY_PROVIDERS:
                clean_value = str(key_value).strip()
                # Preserve an empty value so the user can explicitly clear a key.
                sanitized[provider] = encrypt_secret(clean_value) if clean_value else ""
        return sanitized

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Settings must be a JSON object.")
        # Whitelist filtering: only retain approved top-level keys
        filtered_data = {k: v for k, v in data.items() if k in ALLOWED_SETTINGS_KEYS}
        return super().to_internal_value(filtered_data)


class OrganizationSerializer(serializers.ModelSerializer):
    """Serializer for Organization model."""

    class Meta:
        model = Organization
        fields = ["id", "name"]


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    organization = OrganizationSerializer(read_only=True)
    settings = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()
    passkey_count = serializers.SerializerMethodField()
    needs_passkey = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "name",
            "role",
            "organization",
            "settings",
            "has_password",
            "passkey_count",
            "needs_passkey",
        ]

    def get_settings(self, obj):
        return format_safe_user_settings(obj.settings or {})

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()

    def get_passkey_count(self, obj) -> int:
        return obj.passkeys.count()

    def get_needs_passkey(self, obj) -> bool:
        """Family account whose current session wasn't opened with a passkey."""
        return obj.has_family_role and not getattr(obj, "passkey_session", False)


def _validate_new_email(value: str) -> str:
    email = User.objects.normalize_email(value).strip()
    if User.objects.filter(email__iexact=email).exists():
        raise serializers.ValidationError(
            "An account with this email already exists. Sign in instead."
        )
    return email


def _validate_new_password(password: str, *, email: str, name: str = "") -> None:
    try:
        validate_password(password, User(email=email, name=name))
    except Exception as exc:  # django ValidationError
        raise serializers.ValidationError({"password": list(exc.messages)}) from exc


class JoinSerializer(serializers.Serializer):
    """Validate a visitor joining through a shared invite link.

    A full first and last name is required: whoever took a photo or wrote a note
    may later need to be identified as its author.
    """

    token = serializers.CharField(max_length=128)
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, max_length=128)

    def validate_full_name(self, value: str) -> str:
        name = " ".join(value.split())
        if len(name.split(" ")) < 2:
            raise serializers.ValidationError("Please enter your first and last name.")
        return name

    def validate_email(self, value: str) -> str:
        return _validate_new_email(value)

    def validate(self, attrs):
        _validate_new_password(
            attrs["password"], email=attrs["email"], name=attrs["full_name"]
        )
        return attrs


class ClaimAccountSerializer(serializers.Serializer):
    """Add an email and password to a visitor who joined before passwords existed."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, max_length=128)

    def validate_email(self, value: str) -> str:
        return _validate_new_email(value)

    def validate(self, attrs):
        user = self.context["request"].user
        _validate_new_password(attrs["password"], email=attrs["email"], name=user.name)
        return attrs


class PasskeyCeremonySerializer(serializers.Serializer):
    """The signed state from an options call plus the browser's credential JSON."""

    state = serializers.CharField(max_length=2048)
    credential = serializers.DictField()


class PasskeyRegisterSerializer(PasskeyCeremonySerializer):
    name = serializers.CharField(max_length=100, required=False, allow_blank=True)


class ChangePasswordSerializer(PasskeyCeremonySerializer):
    new_password = serializers.CharField(write_only=True, max_length=128)

    def validate(self, attrs):
        user = self.context["request"].user
        _validate_new_password(attrs["new_password"], email=user.email, name=user.name)
        return attrs


class PasskeySerializer(serializers.ModelSerializer):
    class Meta:
        model = Passkey
        fields = ["id", "name", "created_at", "last_used_at"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
