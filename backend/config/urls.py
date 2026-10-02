"""URL configuration for config project."""

from django.contrib import admin
from django.urls import include, path, re_path

from config.spa import serve_frontend

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.users.urls")),
    path("api/v1/journal/", include("apps.journal.urls")),
    path("api/v1/visits/", include("apps.visits.urls")),
    # Catch-all, last: hands any other path to the built SPA so vue-router
    # can resolve it client-side (e.g. a refresh on /entries/5). Excludes
    # api/ and admin/ so a bad or removed endpoint still 404s normally
    # instead of silently returning the frontend's HTML. Real static assets
    # never reach here in production — WhiteNoise serves those before the
    # URLconf runs. See config.spa and docs/HOSTING.md.
    re_path(r"^(?!api/|admin/).*$", serve_frontend),
]
