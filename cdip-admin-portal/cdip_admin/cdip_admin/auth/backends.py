import json
import base64
from django.contrib.auth.backends import *


class SimpleUserInfoBackend(ModelBackend):
    def authenticate(self, request, user_info=None, **kwargs):
        try:
            if not user_info:
                header = request.META.get('HTTP_X_USERINFO')
                user_info = self.get_user_info(header=header)
            username = user_info.get('username') if user_info else None
            if username:
                user = UserModel.objects.get(email=username)
        except UserModel.DoesNotExist:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a nonexistent user (#20760).
            user = UserModel.objects.create(email=username, username=username)
        else:
            if self.user_can_authenticate(user):
                return user

    def get_user_info(self, *, header=None):
        """
        Extracts the header containing the JSON web token from the given
        request.
        """
        # if isinstance(header, str):
        #     # Work around django test client oddness
        #     header = header.encode(HTTP_HEADER_ENCODING)
        try:
            header = base64.b64decode(header)
            user_info = json.loads(header)
        except:
            pass
        else:
            return user_info
