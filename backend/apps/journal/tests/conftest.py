"""Shared fixtures for the journal app's tests."""

import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Organization
from apps.users.models import Role, User

VALID_PASSWORD = "ValidPassword123!"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def organization():
    return Organization.objects.create(name="Test Family")


@pytest.fixture
def visitor(organization):
    return User.objects.create_user(
        email="maria@visitors.invalid",
        name="Maria Lopez",
        organization=organization,
        role=Role.VISITOR,
    )


@pytest.fixture
def other_visitor(organization):
    return User.objects.create_user(
        email="sam@visitors.invalid",
        name="Sam Rivera",
        organization=organization,
        role=Role.VISITOR,
    )


@pytest.fixture
def family_user(organization):
    return User.objects.create_user(
        email="admin@example.com",
        name="Family Admin",
        password=VALID_PASSWORD,
        organization=organization,
        role=Role.FAMILY,
    )


@pytest.fixture
def other_org_visitor():
    other_org = Organization.objects.create(name="Someone Else's Family")
    return User.objects.create_user(
        email="stranger@visitors.invalid", name="A Stranger", organization=other_org
    )
