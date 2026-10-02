"""Role-based permission classes shared across apps."""

from rest_framework.permissions import BasePermission


class IsFamily(BasePermission):
    """Family accounts (and superusers) only."""

    message = "Only family accounts can do this."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_family)
