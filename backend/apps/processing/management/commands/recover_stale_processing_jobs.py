from django.core.management.base import BaseCommand

from apps.processing.services import recover_stale_jobs


class Command(BaseCommand):
    help = "Recover expired running processing jobs to the durable queued state."

    def add_arguments(self, parser):
        parser.add_argument("--no-dispatch", action="store_true")

    def handle(self, *args, **options):
        recovered = recover_stale_jobs(dispatch=not options["no_dispatch"])
        self.stdout.write(self.style.SUCCESS(f"Recovered {len(recovered)} stale job(s)."))
