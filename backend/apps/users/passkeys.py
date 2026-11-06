"""WebAuthn ceremonies: building options and verifying what the browser returns.

The challenge travels to the browser and back inside a signed, short-lived
`state` string, so nothing has to be stored server-side between the two calls
and it works across gunicorn workers.
"""

import json

from django.conf import settings
from django.core import signing
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .models import Passkey

STATE_MAX_AGE = 300  # seconds the browser has to finish the prompt
INVALID = "That passkey couldn't be verified. Please try again."


def _sign_state(purpose: str, challenge: bytes, user_id: int | None) -> str:
    return signing.dumps(
        {"c": bytes_to_base64url(challenge), "u": user_id}, salt=f"passkey:{purpose}"
    )


def _load_state(purpose: str, state: str) -> dict:
    try:
        return signing.loads(state, salt=f"passkey:{purpose}", max_age=STATE_MAX_AGE)
    except signing.BadSignature as exc:  # includes SignatureExpired
        raise ValidationError({"detail": "The passkey prompt expired. Please try again."}) from exc


def _descriptor(passkey: Passkey) -> PublicKeyCredentialDescriptor:
    transports = []
    for value in passkey.transports or []:
        try:
            transports.append(AuthenticatorTransport(value))
        except ValueError:
            continue
    return PublicKeyCredentialDescriptor(
        id=base64url_to_bytes(passkey.credential_id), transports=transports or None
    )


def registration_options(user) -> dict:
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(user.pk).encode(),
        user_name=user.email,
        user_display_name=user.name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            # Discoverable, so sign-in needs no email first.
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[_descriptor(p) for p in user.passkeys.all()],
    )
    return {
        "options": json.loads(options_to_json(options)),
        "state": _sign_state("register", options.challenge, user.pk),
    }


def register(user, state: str, credential: dict, name: str = "") -> Passkey:
    data = _load_state("register", state)
    if data["u"] != user.pk:
        raise ValidationError({"detail": INVALID})
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(data["c"]),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGINS,
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
        raise ValidationError({"detail": INVALID}) from exc

    transports = credential.get("response", {}).get("transports") or []
    return Passkey.objects.create(
        user=user,
        credential_id=bytes_to_base64url(verified.credential_id),
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=[str(t) for t in transports][:10],
        name=name.strip()[:100] or f"Passkey added {timezone.localdate():%b %-d, %Y}",
    )


def authentication_options(user=None) -> dict:
    """Options for a passkey prompt. With a user, the prompt is limited to their passkeys."""
    allow = [_descriptor(p) for p in user.passkeys.all()] if user else None
    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return {
        "options": json.loads(options_to_json(options)),
        "state": _sign_state("authenticate", options.challenge, None),
    }


def authenticate(state: str, credential: dict) -> Passkey:
    """Verify a passkey assertion and return the matching passkey, or raise."""
    data = _load_state("authenticate", state)
    if not isinstance(credential, dict):
        raise ValidationError({"detail": INVALID})
    passkey = (
        Passkey.objects.select_related("user")
        .filter(credential_id=str(credential.get("id", "")))
        .first()
    )
    if passkey is None:
        raise ValidationError({"detail": INVALID})
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(data["c"]),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGINS,
            credential_public_key=bytes(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except (WebAuthnException, KeyError, TypeError, ValueError) as exc:
        raise ValidationError({"detail": INVALID}) from exc

    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = timezone.now()
    passkey.save(update_fields=["sign_count", "last_used_at"])
    return passkey
