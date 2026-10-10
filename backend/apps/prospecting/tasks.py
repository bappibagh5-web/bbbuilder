from celery import shared_task

from .campaigns import process_due_prospecting_messages


@shared_task(name="prospecting.process_due_messages")
def process_due_prospecting_messages_task():
    return [attempt.pk for attempt in process_due_prospecting_messages(limit=50)]
