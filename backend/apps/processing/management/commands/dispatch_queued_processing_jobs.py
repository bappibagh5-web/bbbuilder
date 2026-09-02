from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.processing.models import ProcessingJob
from apps.processing.services import dispatch_processing_job


class Command(BaseCommand):
    help = "Dispatch durable queued processing jobs that were not recently published."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-seconds", type=int, default=60)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(seconds=max(options["older_than_seconds"], 0))
        jobs = ProcessingJob.objects.filter(status=ProcessingJob.Status.QUEUED).filter(
            Q(last_dispatched_at__isnull=True) | Q(last_dispatched_at__lte=cutoff)
        )
        considered = jobs.count()
        dispatched = sum(dispatch_processing_job(job.pk, force=True) for job in jobs)
        self.stdout.write(
            self.style.SUCCESS(f"Considered {considered} queued job(s); dispatched {dispatched}.")
        )
