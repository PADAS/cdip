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
SECRET_KEY = env("SECRET_KEY")
FERNET_KEYS = env.list('FERNET_KEYS', default=[SECRET_KEY, ])

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=False)

# ALLOWED_HOSTS = ['35.192.111.237']
ALLOWED_HOSTS = [env.str('ALLOWED_HOSTS', default='localhost')]

STATIC_ROOT = '/var/www/static/'

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
KEYCLOAK_ISSUER = env('KEYCLOAK_ISSUER')
KEYCLOAK_SERVER = env('KEYCLOAK_SERVER')
KEYCLOAK_REALM = env('KEYCLOAK_REALM')
KEYCLOAK_CLIENT_ID = env('KEYCLOAK_CLIENT_ID')
KEYCLOAK_CLIENT_SECRET = env('KEYCLOAK_CLIENT_SECRET')

KEYCLOAK_PERMISSIONS_METHOD = "role"

CRISPY_TEMPLATE_PACK = 'bootstrap4'
SOCIAL_AUTH_TRAILING_SLASH = False  # Remove trailing slash from routes
SOCIAL_AUTH_AUTH0_DOMAIN = env('SOCIAL_AUTH_AUTH0_DOMAIN')
SOCIAL_AUTH_AUTH0_KEY = env('SOCIAL_AUTH_AUTH0_KEY')
SOCIAL_AUTH_AUTH0_SECRET = env('SOCIAL_AUTH_AUTH0_SECRET')

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
AUDIENCE = env('JWT_AUDIENCE')
AUTH0_TENANT = env('AUTH0_TENANT')
AUTH0_MANAGEMENT_AUDIENCE = env('AUTH0_MANAGEMENT_AUDIENCE')
AUTH0_MANAGEMENT_CLIENT_ID = env.str('AUTH0_MANAGEMENT_CLIENT_ID')

JWT_AUTH = {
    'JWT_PAYLOAD_GET_USERNAME_HANDLER':
        'cdip_admin.utils.jwt_get_username_from_payload_handler',
    'JWT_DECODE_HANDLER':
        'cdip_admin.utils.jwt_decode_token',
    'JWT_ALGORITHM': 'RS256',
    'JWT_AUDIENCE': env('JWT_AUDIENCE'),
    'JWT_ISSUER': env('JWT_ISSUER'),
    'JWT_AUTH_HEADER_PREFIX': 'Bearer',
}

# Excempt list - URL paths that doesn't need Keycloak Authorization
# KEYCLOAK_BEARER_AUTHENTICATION_EXEMPT_PATHS = [
#     'admin', 'accounts',
#     ]
# CONFIG_DIR = os.path.join(os.path.dirname(__file__),os.pardir)
# KEYCLOAK_CLIENT_PUBLIC_KEY = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAgPnFfQALNHbiAHY2Pq32ka/8PYvuWFuw" \
#                              "/qdLXJxP88lFSEaO66wc8KnXJBsn02DqsOL2qk5tzlORW8EHl/4UuGrZzVFsZCcr6FRJOCowPAU8ksjn81" \
#                              "/BvO1kAD5NNgnBmZ5W8pso4VlVr2Mg7Fs6FXmuxhOvS3G+OpmlXFiYAkV3r2n7SseriS+VjBNBPzV" \
#                              "+skFTZjP6qovi7BME2vW+sAKptmlqBlrHtL8c37ge3eX0n2s+XYkqm+2V94LM9n6E02LwxR4GhLs3UmXgB9h8r" \
#                              "/3J9c0Yn4ydnvEDWJP92d7R7reWzl0TkHnUS8Vd74LET7fzPu3/24XYlEX8BO/UCwIDAQAB"
# KEYCLOAK_CONFIG = {
#     'KEYCLOAK_REALM': 'master',
#     'KEYCLOAK_CLIENT_ID': '***REMOVED***',
#     'KEYCLOAK_DEFAULT_ACCESS': 'ALLOW', # DENY or ALLOW
#     'KEYCLOAK_AUTHORIZATION_CONFIG': os.path.join(CONFIG_DIR , 'authorization-config.json'),
#     'KEYCLOAK_METHOD_VALIDATE_TOKEN': 'DECODE',
#     'KEYCLOAK_SERVER_URL': 'https://cdip-auth.pamdas.org/auth/',
#     'KEYCLOAK_CLIENT_SECRET_KEY': '***REMOVED***',
#     'KEYCLOAK_CLIENT_PUBLIC_KEY': KEYCLOAK_CLIENT_PUBLIC_KEY,
# }

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
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT'),
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
