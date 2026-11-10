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
    without establishing a Django session: a request to an API path with no
    authenticated session user.

    Machine clients (pull-action runners, dispatchers, Cloud Functions) have
    no session, so without this rule every API call is a "first login" --
    auth.login() writes auth_user.last_login (one hot row shared by every
    caller), inserts a django_session row and rotates the CSRF token, per
    request, at ingestion volume. The decision keys on the session user, not
    on cookie presence: a stale or pasted session cookie carries no user and
    must not put a client back on the per-request login path. A browser with
    a live session, or any non-API path, keeps the session login as before.

    Evaluate this while request.user still reflects the session, before the
    middleware replaces it with the header-authenticated user. The prefixes
    are matched against path_info, the URLconf-relative path, so they hold
    under any SCRIPT_NAME mount.
    """
    prefixes = _prefixes()
    if not prefixes:
        return False
    http_request = unwrap_request(request)
    if http_request.user.is_authenticated:
        return False
    return http_request.path_info.startswith(prefixes)
