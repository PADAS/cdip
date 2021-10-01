"""
WSGI config for cdip_admin project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/howto/deployment/wsgi/
"""

import os
import cdip_admin.logconfiguration

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cdip_admin.settings')

cdip_admin.logconfiguration.init()

application = get_wsgi_application()
