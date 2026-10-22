"""Minimal readiness signal for the local proxy and deployment checks."""

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@never_cache
@require_safe
def readiness(request):
    """Expose only availability, never database or application details.

    Anonymous GET/HEAD access is intentional for infrastructure checks.
    Database connection/query timeouts must also be bounded in deployment
    configuration; the HTTP check has its own timeout.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
