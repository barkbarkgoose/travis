"""Create the single family organization, admin accounts and first invite link.

Safe to re-run: existing objects are reused, and a password is only ever set on
newly created admins.

    python manage.py bootstrap_family --org-name "Travis's Family" \\
        --admin "Jake Barker <jake@example.com>"
"""

import re
import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.users.models import Invite, Role, User

ADMIN_PATTERN = re.compile(r"^\s*(?P<name>.+?)\s*<(?P<email>[^<>\s]+)>\s*$")


class Command(BaseCommand):
    help = "Create the family organization, family admin accounts, and an invite link."

    def add_arguments(self, parser):
        parser.add_argument("--org-name", default="Family")
        parser.add_argument(
            "--admin",
            action="append",
            default=[],
            metavar='"Full Name <email>"',
            help="Family admin account to create (repeatable).",
        )
        parser.add_argument(
            "--base-url",
            default="http://localhost:5177",
            help="Used only to print the full join link.",
        )

    @transaction.atomic
    def handle(self, *args, org_name, admin, base_url, **options):
        organization, created = Organization.objects.get_or_create(name=org_name)
        self.stdout.write(
            f"{'Created' if created else 'Using existing'} organization: {organization.name}"
        )

        for spec in admin:
            match = ADMIN_PATTERN.match(spec)
            if not match:
                raise CommandError(f'Could not parse --admin "{spec}". Use "Full Name <email>".')
            email = User.objects.normalize_email(match["email"])
            user = User.objects.filter(email=email).first()
            if user:
                if user.role != Role.FAMILY:
                    user.role = Role.FAMILY
                    user.save(update_fields=["role"])
                self.stdout.write(f"Admin already exists: {email}")
                continue
            password = secrets.token_urlsafe(12)
            User.objects.create_user(
                email=email,
                name=match["name"],
                password=password,
                organization=organization,
                role=Role.FAMILY,
                is_staff=True,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Created admin {email} with password: {password}")
            )
            self.stdout.write("  (shown once. Change it after first login.)")

        invite = organization.invites.filter(revoked_at__isnull=True).first()
        if invite is None:
            invite = Invite.objects.create(organization=organization)
        self.stdout.write(
            self.style.SUCCESS(f"Join link: {base_url.rstrip('/')}/join/{invite.token}")
        )
