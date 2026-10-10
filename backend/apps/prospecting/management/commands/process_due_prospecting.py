from django.core.management.base import BaseCommand

from apps.prospecting.campaigns import process_due_prospecting_messages


class Command(BaseCommand):
    help = "Process a bounded batch of due Prospecting messages."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        attempts = process_due_prospecting_messages(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Processed {len(attempts)} due message(s)."))
