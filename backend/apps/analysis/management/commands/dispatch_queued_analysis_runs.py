from django.core.management.base import BaseCommand

from apps.analysis.models import AnalysisRun
from apps.analysis.services import dispatch_analysis_run


class Command(BaseCommand):
    help = "Dispatch durable queued AI analysis runs."

    def handle(self, *args, **options):
        count = 0
        for run_id in AnalysisRun.objects.filter(status=AnalysisRun.Status.QUEUED).values_list(
            "pk", flat=True
        ):
            count += int(dispatch_analysis_run(run_id))
        self.stdout.write(self.style.SUCCESS(f"Dispatched {count} queued analysis run(s)."))
