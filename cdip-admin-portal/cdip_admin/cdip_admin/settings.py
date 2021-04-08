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

env = environ.Env()
# reading .env file
environ.Env.read_env()

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/


# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY = '***REMOVED***'
SECRET_KEY = env.str("SECRET_KEY", "cfd5266420dffc9baf8137b4eb711498591a0cebaebb14cbdfe74582137d455a")
FERNET_KEYS = env.list('FERNET_KEYS', default=[SECRET_KEY, ])

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=False)

# ALLOWED_HOSTS = ['35.192.111.237']
ALLOWED_HOSTS = [env.str('ALLOWED_HOSTS', default='localhost')]

STATIC_ROOT = '/var/www/static/'

DEFAULT_PAGINATE_BY = 25

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_tables2',
    'crispy_forms',
    'website',
    'integrations',
    'core',
    'organizations',
    'accounts',
    'clients',
    'social_django',
    'django_keycloak.apps.KeycloakAppConfig',
    'phonenumber_field',
    'rest_framework',
    'rest_framework_swagger',
    "bootstrap4",
]

LOGIN_URL = 'keycloak_login'
KEYCLOAK_OIDC_PROFILE_MODEL = 'django_keycloak.OpenIdConnectProfile'
KEYCLOAK_ISSUER = env.str('KEYCLOAK_ISSUER', "https://cdip-auth.pamdas.org/auth/realms/cdip-dev")
KEYCLOAK_SERVER = env.str('KEYCLOAK_SERVER', "https://cdip-auth.pamdas.org")
KEYCLOAK_REALM = env.str('KEYCLOAK_REALM', "cdip-dev")
KEYCLOAK_CLIENT_ID = env.str('KEYCLOAK_CLIENT_ID', "***REMOVED***")
KEYCLOAK_CLIENT_SECRET = env.str('KEYCLOAK_CLIENT_SECRET', "something-fancy")
KEYCLOAK_ADMIN_CLIENT_ID = env.str('KEYCLOAK_ADMIN_CLIENT_ID', "***REMOVED***")
KEYCLOAK_CLIENT_UUID = env.str('KEYCLOAK_CLIENT_UUID', "***REMOVED***")
KEYCLOAK_ADMIN_CLIENT_SECRET = env.str('KEYCLOAK_ADMIN_CLIENT_SECRET', "something-fancy")

KEYCLOAK_PERMISSIONS_METHOD = "role"

CRISPY_TEMPLATE_PACK = 'bootstrap4'

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

JWT_AUTH = {
    'JWT_PAYLOAD_GET_USERNAME_HANDLER':
        'cdip_admin.utils.jwt_get_username_from_payload_handler',
    'JWT_DECODE_HANDLER':
        'cdip_admin.utils.jwt_decode_token',
    'JWT_ALGORITHM': 'RS256',
    'JWT_AUDIENCE': env.str('JWT_AUDIENCE', ""),
    'JWT_ISSUER': env.str('JWT_ISSUER', ""),
    'JWT_AUTH_HEADER_PREFIX': 'Bearer',
}

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_jwt.authentication.JSONWebTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.coreapi.AutoSchema',
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
}

SOCIAL_AUTH_AUTH0_SCOPE = [
    'openid',
    'profile',
    'email'
]

AUTHENTICATION_BACKENDS = {
    'django.contrib.auth.backends.ModelBackend',
    'django.contrib.auth.backends.RemoteUserBackend',
    'cdip_admin.auth.backends.KeycloakAuthorizationCodeBackend',
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django_keycloak.middleware.BaseKeycloakMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.RemoteUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cdip_admin.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'cdip_admin.wsgi.application'

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env.str('DB_NAME', "cdip_portaldb"),
        'USER': env.str('DB_USER', "cdip_dbuser"),
        'PASSWORD': env.str('DB_PASSWORD', "cdip_dbpassword"),
        'HOST': env.str('DB_HOST', "cdip_dbhost"),
        'PORT': env.str('DB_PORT', "5432"),
    }
}

SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'api_key': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'access_token'
        }
    },
}

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGES = (
    ('en', _('English')),
    ('es', _('Spanish'))
)

LANGUAGE_CODE = 'en'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = '/static/'
