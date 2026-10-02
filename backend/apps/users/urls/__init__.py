"""Users app URL configuration."""

from django.urls import path

from apps.users.views import (
    InviteView,
    JoinView,
    LoginView,
    RefreshTokenView,
    UserSettingsView,
)

urlpatterns = [
    path("join/", JoinView.as_view(), name="join"),
    path("invite/", InviteView.as_view(), name="invite"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshTokenView.as_view(), name="refresh"),
    path("settings/", UserSettingsView.as_view(), name="user-settings"),
]
