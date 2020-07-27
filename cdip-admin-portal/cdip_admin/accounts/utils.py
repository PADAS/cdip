import http.client
import json


def get_token():
    conn = http.client.HTTPSConnection("dev-fop-06qh.us.auth0.com")

    payload = "{\"client_id\":\"98b2myE6ZMQk5hCD6goatV7iTUcEejV1\"," \
              "\"client_secret\":\"_oLeoOMp1wLj3h_I-giZtfcvYeElEDorKV1ZV-ZBVXflSBQ2ZNqVvA3fyAnTr20X\"," \
              "\"audience\":\"https://dev-fop-06qh.us.auth0.com/api/v2/\"," \
              "\"grant_type\":\"client_credentials\"}"

    headers = {'content-type': "application/json"}

    conn.request("POST", "/oauth/token", payload, headers)

    res = conn.getresponse()
    data = res.read()

    return data.decode("utf-8")


def get_accounts():
    conn = http.client.HTTPConnection("dev-fop-06qh.us.auth0.com")

    token = get_token()

    headers = {'authorization': "Bearer " + token}

    conn.request("GET", "/api/v2/users", headers=headers)

    res = conn.getresponse()
    data = res.read()

    json_data = json.dumps(data.decode("utf-8"))

    #accounts = (Account(**json.loads(json_data)))

    return None


class Account(object):
    def __init__(self, name: str, email: str):
        self.first_name = name
        self.last_name = email

