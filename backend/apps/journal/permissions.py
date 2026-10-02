"""Object-level permissions for the journal app."""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsEntryAuthorOrFamilyReadOnly(BasePermission):
    """The author can do anything (subject to the edit-window check in the
    view); family can look but not directly edit — corrections from family go
    in as an addendum, same as anyone else, so the author's own account stays
    the primary record.
    """

    message = "Only the person who wrote this entry can edit it."

    def has_object_permission(self, request, view, obj) -> bool:
        if obj.author_id == request.user.id:
            return True
        if request.user.is_family:
            return request.method in SAFE_METHODS
        return False
