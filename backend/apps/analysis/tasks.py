from celery import shared_task

from .models import AnalysisTaskRun
from .services import execute_analysis_run, execute_analysis_task


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def process_analysis_run(self, run_id):
    outcome = execute_analysis_run(run_id)
    if outcome["outcome"] == "retry":
        raise self.retry(countdown=outcome["countdown"], max_retries=None)
    return outcome


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def process_analysis_page_task(self, task_id):
    outcome = execute_analysis_task(task_id, AnalysisTaskRun.TaskType.PAGE_ANALYSIS)
    if outcome["outcome"] in ("retry", "retry_dispatch"):
        raise self.retry(countdown=outcome["countdown"], max_retries=None)
    return outcome


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def process_analysis_synthesis_task(self, task_id):
    outcome = execute_analysis_task(task_id, AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS)
    if outcome["outcome"] == "retry":
        raise self.retry(countdown=outcome["countdown"], max_retries=None)
    return outcome
