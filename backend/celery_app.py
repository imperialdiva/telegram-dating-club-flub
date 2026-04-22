from celery import Celery
from celery.schedules import crontab

from db import CELERY_BROKER_URL, CELERY_RESULT_BACKEND


celery_app = Celery(
    "club_flub",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "recalculate-all-ratings-hourly": {
            "task": "tasks.recalculate_all_ratings",
            "schedule": crontab(minute=0),
        },
    },
)
