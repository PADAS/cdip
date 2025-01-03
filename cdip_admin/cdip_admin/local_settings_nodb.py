import environ
from cdip_admin.settings import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "dummy-database",
    }
}

GCP_ENVIRONMENT_ENABLED = env.bool("GCP_ENVIRONMENT_ENABLED", default=False)
TRACING_ENABLED = env.bool("TRACING_ENABLED", False)
PUBSUB_ENABLED = env.bool("PUBSUB_ENABLED", False)
