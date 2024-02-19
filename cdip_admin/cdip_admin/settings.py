"""
Django settings for cdip_admin project.

Generated by 'django-admin startproject' using Django 3.0.7.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.0/ref/settings/
"""

import os
import environ
from pathlib import Path
from django.utils.translation import ugettext_lazy as _
from kombu import Exchange, Queue

env = environ.Env()
# reading .env file
environ.Env.read_env()

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/


# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY = '^$pu=5yw^4cl1&7e#89&-&8*&_*&_hwas*fv!h-=zsl6j2hg0b'
SECRET_KEY = env.str(
    "SECRET_KEY", "cfd5266420dffc9baf8137b4eb711498591a0cebaebb14cbdfe74582137d455a"
)
FERNET_KEYS = env.list(
    "FERNET_KEYS",
    default=[
        SECRET_KEY,
    ],
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=False)

# Defaults are sensible for local development.
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=[
        "localhost",
        "portal-127.0.0.1.nip.io",
    ],
)

# Tell Django to use Host forwarded from proxy or gateway)
USE_X_FORWARDED_HOST = True

# Set forwarded protocol header (Override this in you local dev if using http.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

STATIC_ROOT = "/var/www/static/"

DEFAULT_PAGINATE_BY = 25

# Application definition

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django_tables2",
    "django_filters",
    "crispy_forms",
    "website",
    "integrations",
    "core",
    "organizations",
    "accounts",
    "clients",
    "phonenumber_field",
    "rest_framework",
    "rest_framework_swagger",
    "sync_integrations",
    "bootstrap4",
    "cdip_admin",
    "django_extensions",
    "simple_history",
    "django_jsonform",
    "django_celery_beat",
    "storages",
    "deployments",
    "activity_log",
]


KEYCLOAK_SERVER = env.str("KEYCLOAK_SERVER", "https://cdip-auth.pamdas.org")
KEYCLOAK_REALM = env.str("KEYCLOAK_REALM", "cdip-dev")
KEYCLOAK_CLIENT_ID = env.str("KEYCLOAK_CLIENT_ID", "cdip-admin-portal")
KEYCLOAK_CLIENT_SECRET = env.str("KEYCLOAK_CLIENT_SECRET", "something-fancy")
KEYCLOAK_ADMIN_CLIENT_ID = env.str("KEYCLOAK_ADMIN_CLIENT_ID", "admin-cli")
# KEYCLOAK_CLIENT_UUID = env.str(
#     'KEYCLOAK_CLIENT_UUID', "90d34a81-c70c-408b-ad66-7fa1bfe58892")
KEYCLOAK_ADMIN_CLIENT_SECRET = env.str(
    "KEYCLOAK_ADMIN_CLIENT_SECRET", "something-fancy"
)

CRISPY_TEMPLATE_PACK = "bootstrap4"

LOGIN_URL = "/login"
LOGIN_REDIRECT_URL = "/"
# LOGOUT_REDIRECT_URL = "/"

KONG_PROXY_URL = env.str(
    "KONG_PROXY_URL", "http://kong-proxy.kong.svc.cluster.local:8001"
)


REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "cdip_admin.auth.authentication.SimpleUserInfoAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ),
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.coreapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "proxy_pagination.ProxyPagination",
    'PAGE_SIZE': 20
}

PROXY_PAGINATION_PARAM = 'pager'
PROXY_PAGINATION_DEFAULT = 'rest_framework.pagination.CursorPagination'
PROXY_PAGINATION_MAPPING = {
    'cursor': 'rest_framework.pagination.CursorPagination',
    'limit': 'rest_framework.pagination.LimitOffsetPagination',
    'page': 'rest_framework.pagination.PageNumberPagination',
}

AUTHENTICATION_BACKENDS = {
    "django.contrib.auth.backends.ModelBackend",
    "cdip_admin.auth.backends.SimpleUserInfoBackend",
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "api.v2.middleware.ApiIntegrationIdMiddleware",
    "cdip_admin.auth.middleware.AuthenticationMiddleware",
    "cdip_admin.auth.middleware.OidcRemoteUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "crum.CurrentRequestUserMiddleware",
]

ROOT_URLCONF = "cdip_admin.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        'DIRS': [os.path.join(BASE_DIR, 'emails/templates')],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "cdip_admin.wsgi.application"

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.str("DB_NAME", "cdip_portaldb"),
        "USER": env.str("DB_USER", "cdip_dbuser"),
        "PASSWORD": env.str("DB_PASSWORD", "cdip_dbpassword"),
        "HOST": env.str("DB_HOST", "cdip_dbhost"),
        "PORT": env.str("DB_PORT", "5432"),
    }
}

SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "api_key": {"type": "apiKey", "in": "header", "name": "access_token"}
    },
}

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGES = (("en", _("English")), ("es", _("Spanish")))

LANGUAGE_CODE = "en"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = "/static/"

# Celery Settings
CELERY_BROKER_URL = env.str("CELERY_BROKER_URL", "redis://celery-redis:6379")

CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ENABLE_UTC = True
CELERY_TIMEZONE = "UTC"

CELERY_REDIS_MAX_CONNECTIONS = 100
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100

CELERY_RESULT_PERSISTENT = False
CELERY_RESULT_EXPIRES = 300
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED = True
# TODO: update in production
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# Enables error emails.
CELERY_SEND_TASK_ERROR_EMAILS = False

CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_DEFAULT_EXCHANGE = "default"
CELERY_TASK_DEFAULT_ROUTING_KEY = "default"

CELERY_TASK_QUEUES = (
    Queue("default", Exchange("default"), routing_key="default"),
    Queue("deployments", Exchange("deployments"), routing_key="deployments"),
    Queue("mb_permissions", Exchange("mb_permissions"), routing_key="mb_permissions"),
)

CELERY_TASK_ROUTES = {
    "deployments.tasks.deploy_serverless_dispatcher": {
        "queue": "deployments", "routing_key": "deployments"
    },
    "deployments.tasks.delete_serverless_dispatcher": {
        "queue": "deployments", "routing_key": "deployments"
    },
    "integrations.tasks.recreate_and_send_movebank_permissions_csv_file": {
        "queue": "mb_permissions", "routing_key": "mb_permissions"
    },
    "integrations.tasks.update_mb_permissions_for_group": {
        "queue": "mb_permissions", "routing_key": "mb_permissions"
    },
}

CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600, "fanout_prefix": True}

# task:
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SYNC_INTEGRATION_INTERVAL_MINUTES = env.int(
    "CELERY_TASK_SYNC_INTEGRATION_INTERVAL_MINUTES", 60
)

USE_SMART_CACHE = env.bool("USE_SMART_CACHE", False)

# Email settings
EMAIL_HOST = env.str("EMAIL_HOST", "email-smtp.us-west-2.amazonaws.com")
EMAIL_PORT = env.int("EMAIL_PORT", 2587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", "")
EMAIL_FROM_DEFAULT = env.str("EMAIL_FROM_DEFAULT", "notifications.cdip@pamdas.org")
EMAIL_FROM_DISPLAY_DEFAULT = env.str("EMAIL_FROM_DISPLAY_DEFAULT", "Gundi Notifications")
EMAIL_REPLY_DEFAULT = env.str("EMAIL_REPLY_DEFAULT", "noreply@tempuri.org")
EMAIL_INVITE_REDIRECT_URL = env.str("EMAIL_INVITE_REDIRECT_URL", "https://cdip-prod01.pamdas.org")

# Used for storing files such as report attachments
DEFAULT_FILE_STORAGE = "storages.backends.gcloud.GoogleCloudStorage"
GS_BUCKET_NAME = env.str("GS_BUCKET_NAME", "cdip-files-dev")

# Settings for stream, where this API writes.
REDIS_HOST = env.str("REDIS_HOST", "localhost")
REDIS_PORT = env.int("REDIS_PORT", 6379)
REDIS_DB = env.int("REDIS_DB", 0)

# Settings for redis cache and deduplication
STREAMS_DEFAULT_MAXLEN = env.int("STREAMS_DEFAULT_MAXLEN", 10000)
GEOEVENT_STREAM_DEFAULT_MAXLEN = env.int("GEOEVENT_STREAM_DEFAULT_MAXLEN", 10000)

# N-seconds window to keep hash of position record for duplicate detection.
POSITIONS_DUPLICATE_CHECK_SECONDS = env.int("POSITIONS_DUPLICATE_CHECK_SECONDS", 1800)
# N-seconds window to keep hash of Geo Event record for duplicate detection.
GEOEVENT_DUPLICATE_CHECK_SECONDS = env.int("GEOEVENT_DUPLICATE_CHECK_SECONDS", 3600)
# N-seconds window to keep hash of Message record for duplicate detection.
MESSAGES_DUPLICATE_CHECK_SECONDS = env.int("MESSAGES_DUPLICATE_CHECK_SECONDS", 1800)
# N-seconds window to keep hash of camera trap record for duplicate detection.
CAMERA_TRAP_DUPLICATE_CHECK_SECONDS = env.int("CAMERA_TRAP_DUPLICATE_CHECK_SECONDS", 1800)
# N-seconds window to keep hash of generic sensor record for duplicate detection.
OBSERVATION_DUPLICATE_CHECK_SECONDS = env.int("OBSERVATION_DUPLICATE_CHECK_SECONDS", 1800)

# Used in OTel traces/spans to set the 'environment' attribute, used on metrics calculation
TRACE_ENVIRONMENT = env.str("TRACE_ENVIRONMENT", "dev")
TRACING_ENABLED = env.bool("TRACING_ENABLED", True)

# Subscriptions to read system events from pub/sub topics
GCP_PROJECT_ID = env.str("GCP_PROJECT_ID", "cdip-78ca")
DISPATCHER_EVENTS_SUB_ID = env.str("DISPATCHER_EVENTS_SUB_ID", "cdip-dispatcher-events-sub-prod")
INTEGRATION_EVENTS_SUB_ID = env.str("INTEGRATION_EVENTS_SUB_ID", "cdip-integration-events-sub-prod")
GCP_ENVIRONMENT_ENABLED = env.bool("GCP_ENVIRONMENT_ENABLED", default=True)
DISPATCHER_DEFAULTS_SECRET = env.str("DISPATCHER_DEFAULTS_SECRET", "er-dispatcher-defaults-prod")
DISPATCHER_DEFAULTS_SECRET_SMART = env.str("DISPATCHER_DEFAULTS_SECRET_SMART", "sm-dispatcher-defaults-prod")
MOVEBANK_DISPATCHER_DEFAULT_TOPIC = env.str("MOVEBANK_DISPATCHER_DEFAULT_TOPIC", "movebank-dispatcher-topic-prod")
