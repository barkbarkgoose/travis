"""Serves the built Vue app's index.html for routes vue-router handles
client-side, so a direct hit or a page refresh on e.g. /entries/5 doesn't
404 — the browser gets the same single-page app either way and vue-router
resolves the URL itself once it loads. See docs/HOSTING.md.

Real files (the JS/CSS bundle under /assets/, robots.txt, ...) are served by
WhiteNoise before a request ever reaches this — see WHITENOISE_ROOT in
config.settings.production. This view only ever runs for paths that aren't a
file on disk and aren't /admin/ or /api/, matching config.urls' ordering.
"""

from django.conf import settings
from django.http import HttpResponse

_FRONTEND_NOT_BUILT = (
    "Frontend build not found at {path}.\n\n"
    "Run `pnpm build` in frontend/ (or, for local development, use ./dev.sh "
    "instead — it runs Vite's own dev server and never hits this view)."
)


def serve_frontend(request, *args, **kwargs):
    index_path = settings.FRONTEND_DIST_DIR / "index.html"
    try:
        html = index_path.read_text()
    except FileNotFoundError:
        return HttpResponse(
            _FRONTEND_NOT_BUILT.format(path=index_path),
            status=501,
            content_type="text/plain",
        )
    return HttpResponse(html)
