"""Object-level permissions for the visits app."""

from rest_framework.permissions import BasePermission


class IsVisitOwnerOrFamily(BasePermission):
    """The visitor who booked it can change their own booking; family can
    change anyone's (including blocks, which no visitor owns)."""

    message = "You can only change your own booking."

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.is_family:
            return True
        return obj.user_id == request.user.id
