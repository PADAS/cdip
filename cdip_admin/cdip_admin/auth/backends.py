import json
import base64
import hashlib
from django.conf import settings
from django.contrib.auth.backends import *
from django.core.cache import cache

from clients.models import ClientProfile

import logging

logger = logging.getLogger(__name__)


def _cache_key(prefix, value):
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return f"auth:{prefix}:{digest}"


class SimpleUserInfoBackend(ModelBackend):
    def authenticate(self, request, user_info=None, **kwargs):
        # Parsing the token is cheap and never touches the DB. A failure here
        # means we genuinely can't identify the caller -> not authenticated.
        try:
            if not user_info:
                if hasattr(request, "META"):
                    header = request.META.get("HTTP_X_USERINFO")
                    user_info = self.get_user_info(header=header)
                else:
                    return None

            username = user_info.get("username") if user_info else None
            if not username:
                return None

            email = user_info.get("email") if user_info else None
            if not email or "@" not in email:
                email = username if "@" in username else f"{username}@sintegrate.org"

            client_id = user_info.get("client_id") if user_info else None
        except Exception:
            logger.exception("Failure parsing user_info in remote user backend. user_info: %s", user_info)
            return None

        # Identity resolution below hits the DB on every request. It is cached so
        # the high-volume ingestion path doesn't query Postgres per request, and
        # transient DB errors are allowed to propagate (surfaced as a retryable
        # 5xx) rather than being swallowed into a misleading auth failure.
        user = self._get_or_create_user(email, username)

        if client_id and self._client_profile_exists(client_id):
            request.session["client_id"] = client_id

        if user is not None and self.user_can_authenticate(user):
            return user
        return None

    def _get_or_create_user(self, email, username):
        if not email:
            return None
        ttl = getattr(settings, "AUTH_IDENTITY_CACHE_TTL", 0)
        cache_key = _cache_key("user", email) if ttl > 0 else None
        if cache_key:
            user = cache.get(cache_key)
            if user is not None:
                return user
        user, _ = UserModel.objects.get_or_create(
            email=email, defaults={"username": username}
        )
        if cache_key:
            cache.set(cache_key, user, ttl)
        return user

    def _client_profile_exists(self, client_id):
        ttl = getattr(settings, "AUTH_IDENTITY_CACHE_TTL", 0)
        cache_key = _cache_key("client_profile_exists", client_id) if ttl > 0 else None
        if cache_key:
            exists = cache.get(cache_key)
            if exists is not None:
                return exists
        exists = ClientProfile.objects.filter(client_id=client_id).exists()
        if cache_key:
            cache.set(cache_key, exists, ttl)
        return exists

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
