from django.conf import settings


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
    """
    prefixes = tuple(getattr(settings, "STATELESS_AUTH_PATH_PREFIXES", ()) or ())
    if not prefixes:
        return False
    # DRF wraps the Django request; the cookies and path live on the inner one.
    http_request = getattr(request, "_request", request)
    cookies = getattr(http_request, "COOKIES", None) or {}
    if settings.SESSION_COOKIE_NAME in cookies:
        return False
    return (getattr(http_request, "path", "") or "").startswith(prefixes)
