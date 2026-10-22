"""Infrastructure readiness must not expose private data or serve SPA HTML."""

from unittest.mock import patch

import pytest
from django.db import OperationalError


@pytest.mark.django_db
def test_readiness_allows_anonymous_database_check(client):
    response = client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "no-store" in response["Cache-Control"]


def test_readiness_database_failure_is_generic_and_not_cached(client):
    with patch("config.health.connection.cursor", side_effect=OperationalError("secret-db-host:password")):
        response = client.get("/health/")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"secret-db-host" not in response.content
    assert "no-store" in response["Cache-Control"]


@pytest.mark.django_db
def test_readiness_supports_head(client):
    response = client.head("/health/")

    assert response.status_code == 200
    assert response.content == b""
    assert "no-store" in response["Cache-Control"]


def test_readiness_rejects_writes_without_accessing_database(client):
    with patch("config.health.connection.cursor") as cursor:
        response = client.post("/health/", {})

    assert response.status_code == 405
    cursor.assert_not_called()
    assert "no-store" in response["Cache-Control"]
