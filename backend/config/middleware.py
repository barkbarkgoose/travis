"""Small response-header middleware used only in production.

See config.settings.production for why these live in Django itself rather
than a reverse proxy: shared hosting gives you no proxy layer to configure.
"""


class NoIndexHeaderMiddleware:
    """Adds X-Robots-Tag: noindex, nofollow to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response
