"""Users app URL configuration."""

from django.urls import path

from apps.users.views import (
    AdminSessionView,
    ChangePasswordView,
    ClaimAccountView,
    InviteView,
    JoinView,
    LoginView,
    PasskeyAuthOptionsView,
    PasskeyDetailView,
    PasskeyListView,
    PasskeyLoginView,
    PasskeyRegisterOptionsView,
    RefreshTokenView,
    UserSettingsView,
)

urlpatterns = [
    path("join/", JoinView.as_view(), name="join"),
    path("invite/", InviteView.as_view(), name="invite"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshTokenView.as_view(), name="refresh"),
    path("settings/", UserSettingsView.as_view(), name="user-settings"),
    path("account/", ClaimAccountView.as_view(), name="claim-account"),
    path("password/", ChangePasswordView.as_view(), name="change-password"),
    path("admin-session/", AdminSessionView.as_view(), name="admin-session"),
    path("passkeys/", PasskeyListView.as_view(), name="passkeys"),
    path("passkeys/<int:pk>/", PasskeyDetailView.as_view(), name="passkey-detail"),
    path(
        "passkeys/register/options/",
        PasskeyRegisterOptionsView.as_view(),
        name="passkey-register-options",
    ),
    path("passkeys/auth/options/", PasskeyAuthOptionsView.as_view(), name="passkey-auth-options"),
    path("passkeys/login/", PasskeyLoginView.as_view(), name="passkey-login"),
]
