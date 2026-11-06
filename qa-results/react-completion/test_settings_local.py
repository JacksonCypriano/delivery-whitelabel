from config.settings.test import *
SECRET_KEY='isolated-test-environment-only'
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
CELERY_BROKER_URL='memory://'
CELERY_RESULT_BACKEND='cache+memory://'
