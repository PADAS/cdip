from rest_framework.utils import json

import json
import base64
from django.conf import settings
from django.contrib import auth
from django.contrib.auth import load_backend
from django.contrib.auth.backends import RemoteUserBackend
from django.core.exceptions import ImproperlyConfigured
from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import SimpleLazyObject

import logging

logger = logging.getLogger(__name__)


def get_user(request):
    if not hasattr(request, "_cached_user"):
        request._cached_user = auth.get_user(request)
    return request._cached_user


class AuthenticationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        assert hasattr(request, "session"), (
            "The Django authentication middleware requires session middleware "
            "to be installed. Edit your MIDDLEWARE%s setting to insert "
            "'django.contrib.sessions.middleware.SessionMiddleware' before "
            "'django.contrib.auth.middleware.AuthenticationMiddleware'."
        ) % ("_CLASSES" if settings.MIDDLEWARE is None else "")
        request.user = SimpleLazyObject(lambda: get_user(request))


class OidcRemoteUserMiddleware(MiddlewareMixin):
    """
    Middleware for utilizing Web-server-provided authentication.
    If request.user is not authenticated, then this middleware attempts to
    authenticate the username passed in the ``REMOTE_USER`` request header.
    If authentication is successful, the user is automatically logged in to
    persist the user in the session.
    The header used is configurable and defaults to ``REMOTE_USER``.  Subclass
    this class and change the ``header`` attribute if you need to use a
    different header.
    """

    # Name of request header to grab username from.  This will be the key as
    # used in the request.META dictionary, i.e. the normalization of headers to
    # all uppercase and the addition of "HTTP_" prefix apply.
    header = "HTTP_X_USERINFO"
    force_logout_if_no_header = True

    def process_request(self, request):
        # AuthenticationMiddleware is required so that request.user exists.
        if not hasattr(request, "user"):
            raise ImproperlyConfigured(
                "The Django remote user auth middleware requires the"
                " authentication middleware to be installed.  Edit your"
                " MIDDLEWARE setting to insert"
                " 'django.contrib.auth.middleware.AuthenticationMiddleware'"
                " before the RemoteUserMiddleware class."
            )
        try:
            user_info = request.META[self.header]
            if user_info:
                user_info = base64.b64decode(user_info)
                user_info = json.loads(user_info)
                username = user_info["username"]
                # logger.debug('User-info: %s', user_info)
        except KeyError:
            # If specified header doesn't exist then remove any existing
            # authenticated remote-user, or return (leaving request.user set to
            # AnonymousUser by the AuthenticationMiddleware).
            if self.force_logout_if_no_header and request.user.is_authenticated:
                self._remove_invalid_user(request)
            return
        # If the user is already authenticated and that user is the user we are
        # getting passed in the headers, then the correct user is already
        # persisted in the session and we don't need to continue.
        if request.user.is_authenticated:
            if request.user.get_username() == username:
                return
            # Otherwise fall through and re-resolve: the stored Django username
            # may simply differ from the `username` claim. The backend matches
            # users by email, not username, so a username comparison is not a
            # reliable identity check -- compare the resolved user below.
        # Remember who (if anyone) is already authenticated so we only re-login
        # when the session user actually changes.
        current_user_pk = request.user.pk if request.user.is_authenticated else None
        # Attempt to authenticate the user from the header.
        user = auth.authenticate(request, user_info=user_info)
        if user:
            request.user = user
            if user.pk != current_user_pk:
                # New or changed session user. auth.login() calls
                # rotate_token(); calling it on every request -- as happens when
                # the stored username differs from the `username` claim -- keeps
                # regenerating the CSRF secret, so an already-rendered form
                # fails on submit with "CSRF token from POST incorrect."
                # Only rotate when the user genuinely changes.
                auth.login(request, user)
        elif current_user_pk is not None:
            # Header user could not be authenticated but a stale user remains in
            # the session -- drop it.
            self._remove_invalid_user(request)

    def clean_username(self, username, request):
        """
        Allow the backend to clean the username, if the backend defines a
        clean_username method.
        """
        backend_str = request.session[auth.BACKEND_SESSION_KEY]
        backend = auth.load_backend(backend_str)
        try:
            username = backend.clean_username(username)
        except AttributeError:  # Backend has no clean_username method.
            pass
        return username

    def _remove_invalid_user(self, request):
        """
        Remove the current authenticated user in the request which is invalid
        but only if the user is authenticated via the RemoteUserBackend.
        """
        try:
            stored_backend = load_backend(
                request.session.get(auth.BACKEND_SESSION_KEY, "")
            )
        except ImportError:
            # backend failed to load
            auth.logout(request)
        else:
            if isinstance(stored_backend, RemoteUserBackend):
                auth.logout(request)


class PersistentRemoteUserMiddleware(OidcRemoteUserMiddleware):
    """
    Middleware for Web-server provided authentication on logon pages.
    Like RemoteUserMiddleware but keeps the user authenticated even if
    the header (``REMOTE_USER``) is not found in the request. Useful
    for setups when the external authentication via ``REMOTE_USER``
    is only expected to happen on some "logon" URL and the rest of
    the application wants to use Django's authentication mechanism.
    """

    force_logout_if_no_header = False
