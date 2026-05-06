import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# We expect a REDIS_URL environment variable for production, or fallback to localhost
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery app
celery_app = Celery(
    "metricsleuth_worker",
    broker=redis_url,
    backend=redis_url,
    include=["api.tasks"]
)

# Optional: Configuration optimizations for Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=3600,  # 1 hour max
)
