"""JWT authentication that records how the session was opened."""

from rest_framework_simplejwt.authentication import JWTAuthentication

# Claim added to tokens issued after a passkey check (see views._token_payload).
PASSKEY_CLAIM = "amr"
PASSKEY_VALUE = "passkey"


class PasskeyAwareJWTAuthentication(JWTAuthentication):
    """Mark `request.user.passkey_session` so family powers can require a passkey."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        user.passkey_session = token.get(PASSKEY_CLAIM) == PASSKEY_VALUE
        return user, token
