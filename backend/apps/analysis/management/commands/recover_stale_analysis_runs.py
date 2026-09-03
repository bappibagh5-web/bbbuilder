from django.core.management.base import BaseCommand

from apps.analysis.services import recover_stale_analysis_runs


class Command(BaseCommand):
    help = "Recover AI analysis runs whose worker lease expired."

    def handle(self, *args, **options):
        recovered = recover_stale_analysis_runs()
        self.stdout.write(self.style.SUCCESS(f"Recovered {len(recovered)} analysis run(s)."))
