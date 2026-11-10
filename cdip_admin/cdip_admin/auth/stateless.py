from django.conf import settings


def unwrap_request(request):
    """
    The Django HttpRequest behind a DRF Request (or the request itself).

    Middleware, the auth backend and DRF permissions all see the same call
    through different wrappers; attributes shared between them (client_id,
    cookies, path) live on the inner request.
    """
    return getattr(request, "_request", request)


def _prefixes():
    """
    The configured prefixes as a tuple of stripped, non-empty strings. A
    single string stays one prefix: iterating it would yield "/" and match
    every path.
    """
    configured = getattr(settings, "STATELESS_AUTH_PATH_PREFIXES", ()) or ()
    if isinstance(configured, str):
        configured = (configured,)
    return tuple(p.strip() for p in configured if p and p.strip())


def is_stateless_request(request):
    """
    True for requests that should authenticate from the Kong-provided header
    without establishing a Django session: a request to an API path that
    carries no session cookie.

    Machine clients (pull-action runners, dispatchers, Cloud Functions) never
    send a session cookie, so without this rule every API call is a "first
    login" -- auth.login() writes auth_user.last_login (one hot row shared by
    every caller), inserts a django_session row and rotates the CSRF token,
    per request, at ingestion volume. Browser traffic is unaffected: with a
    session cookie, or on any non-API path, the session login runs as before.

    The prefixes are matched against path_info, the URLconf-relative path, so
    they hold under any SCRIPT_NAME mount.
    """
    prefixes = _prefixes()
    if not prefixes:
        return False
    http_request = unwrap_request(request)
    cookies = getattr(http_request, "COOKIES", None) or {}
    if settings.SESSION_COOKIE_NAME in cookies:
        return False
    return (getattr(http_request, "path_info", "") or "").startswith(prefixes)
