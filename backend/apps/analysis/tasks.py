from celery import shared_task

from .services import execute_analysis_run


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def process_analysis_run(self, run_id):
    outcome = execute_analysis_run(run_id)
    if outcome["outcome"] == "retry":
        raise self.retry(countdown=outcome["countdown"], max_retries=None)
    return outcome
