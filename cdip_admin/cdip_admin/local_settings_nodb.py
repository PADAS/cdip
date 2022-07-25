import environ
from cdip_admin.settings import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "dummy-database",
    }
}
