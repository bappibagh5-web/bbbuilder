from celery import shared_task

from .models import ProcessingJob
from .services import execute_processing_job


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def process_processing_job(self, job_id):
    outcome = execute_processing_job(job_id)
    if outcome["outcome"] == "retry":
        job = ProcessingJob.objects.get(pk=job_id)
        raise self.retry(
            countdown=outcome["countdown"],
            max_retries=max(job.max_attempts - 1, 0),
        )
    return outcome
