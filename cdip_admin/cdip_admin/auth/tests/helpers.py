import base64
import json


def userinfo_header(username, email, client_id=None):
    """The X-Userinfo header Kong forwards: base64 of the user-info JSON."""
    payload = {"username": username, "email": email}
    if client_id:
        payload["client_id"] = client_id
    return base64.b64encode(json.dumps(payload).encode("utf-8"))
