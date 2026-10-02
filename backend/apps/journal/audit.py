"""Helper for writing to the append-only audit trail.

Every call site should read like "what happened, to what, done by whom" — see
`docs/SECURITY_AND_LEGAL.md` on why this exists: an audit log of edits, addenda,
and photo actions is part of what makes the record credible later.
"""

from __future__ import annotations

from django.db import models

from .models import AuditEvent


def client_ip(request) -> str | None:
    """Best-effort caller IP. `X-Forwarded-For` is trusted only because
    `REST_FRAMEWORK["NUM_PROXIES"]` tells DRF's throttling the same thing about
    this deployment's reverse proxy; set it before relying on this in production.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_audit(
    *,
    actor,
    action: str,
    obj: models.Model,
    metadata: dict | None = None,
    request=None,
) -> AuditEvent:
    return AuditEvent.objects.create(
        organization=actor.organization,
        actor=actor,
        actor_name=actor.name,
        action=action,
        object_type=type(obj).__name__.lower(),
        object_id=str(obj.pk),
        metadata=metadata or {},
        ip_address=client_ip(request) if request is not None else None,
    )
