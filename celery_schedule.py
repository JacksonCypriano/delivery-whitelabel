from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'sync-ai-knowledge': {
        'task': 'apps.ml_engine.tasks.sync_ai_knowledge',
        'schedule': crontab(minute=0, hour='*/3'),
    },
}