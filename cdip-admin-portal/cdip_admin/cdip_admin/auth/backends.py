import json
import base64
from django.contrib.auth.backends import *

from clients.models import ClientProfile

import logging

logger = logging.getLogger(__name__)


class SimpleUserInfoBackend(ModelBackend):
    def authenticate(self, request, user_info=None, **kwargs):
        try:

            if not user_info:

                if hasattr(request, 'META'):
                    header = request.META.get('HTTP_X_USERINFO')
                    user_info = self.get_user_info(header=header)
                else:
                    return None

            email = user_info.get('email')
            username = user_info.get('username') if user_info else None

            if not email or not '@' in email:
                email = username if '@' in username else f'{username}@sintegrate.org'


            client_id = user_info.get('client_id') if user_info else None
            if email:
                user, created = UserModel.objects.get_or_create(email=email,
                                                       defaults={'username': username})


            if client_id:
                try:
                    client_profile = ClientProfile.objects.get(client_id=client_id)
                    if client_profile:
                        request.session['client_id'] = client_id
                except ClientProfile.DoesNotExist:
                    pass
        except Exception as e:
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a nonexistent user (#20760).
            logger.exception('Failure in remote user backend. user_info: %s', user_info)
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
