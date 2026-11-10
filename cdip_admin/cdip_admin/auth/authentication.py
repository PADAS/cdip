from django.contrib.auth import authenticate, get_user_model

from django.utils.translation import gettext_lazy as _
from rest_framework import HTTP_HEADER_ENCODING, authentication, exceptions, status
import base64
import json

from cdip_admin.auth.backends import SimpleUserInfoBackend


class SimpleUserInfoAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request, user_info=None):
        user = SimpleUserInfoBackend().authenticate(request, user_info=user_info)
        if user is None:
            # DRF treats any tuple as a successful authentication, so a
            # rejected header must not become request.user = None.
            return None
        return (user, user_info)
