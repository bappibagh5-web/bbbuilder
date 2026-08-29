from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Membership, Organization


class Command(BaseCommand):
    help = "Create or update an organization and membership for an existing user."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument("--legal-name", default="")
        parser.add_argument("--timezone", default="America/Vancouver")
        parser.add_argument("--role", choices=Membership.Role.values, default=Membership.Role.ADMIN)

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(email__iexact=options["email"])
        except user_model.DoesNotExist as error:
            raise CommandError("Create the user first with createsuperuser.") from error

        organization, created = Organization.objects.update_or_create(
            slug=options["slug"],
            defaults={
                "name": options["name"],
                "legal_name": options["legal_name"],
                "default_timezone": options["timezone"],
                "status": Organization.Status.ACTIVE,
            },
        )
        membership, membership_created = Membership.objects.update_or_create(
            organization=organization,
            user=user,
            defaults={"role": options["role"], "is_active": True, "ends_at": None},
        )
        action = "Created" if created else "Updated"
        membership_action = "created" if membership_created else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {organization.name}; {membership_action} "
                f"{membership.get_role_display()} membership for {user.email}."
            )
        )
