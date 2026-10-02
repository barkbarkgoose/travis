"""Visits app serializers."""

from __future__ import annotations

from rest_framework import serializers

from .models import Visit, VisitStatus


class VisitSerializer(serializers.ModelSerializer):
    """Read representation."""

    is_past = serializers.BooleanField(read_only=True)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Visit
        fields = [
            "id",
            "user_name",
            "start",
            "end",
            "note",
            "kind",
            "status",
            "is_past",
            "can_edit",
            "created_at",
        ]
        read_only_fields = fields

    def get_can_edit(self, obj: Visit) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        if obj.status == VisitStatus.CANCELLED or obj.is_past:
            return False
        return bool(user.is_family or obj.user_id == user.id)


class VisitWriteSerializer(serializers.ModelSerializer):
    """Create/update representation. `kind` defaults to a normal visit; only
    family may set it to `blocked` — enforced in the view, since that check
    needs the request user, not just the field value.
    """

    class Meta:
        model = Visit
        fields = ["start", "end", "note", "kind"]

    def validate(self, attrs: dict) -> dict:
        start = attrs.get("start", getattr(self.instance, "start", None))
        end = attrs.get("end", getattr(self.instance, "end", None))
        if start and end and end <= start:
            raise serializers.ValidationError("End time must be after the start time.")
        return attrs
