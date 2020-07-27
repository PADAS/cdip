import time
from datetime import datetime, timedelta
import pytz
import json
import random
import requests
import statistics

timing = []

from environs import Env

env = Env()
env.read_env()


AUTH0_API_AUDIENCE = env.str('AUTH0_API_AUDIENCE')
AUTH0_DOMAIN = env.str('AUTH0_DOMAIN')


with env.prefixed('PRODUCER_'):
    AUTH0_CLIENT_ID = env.str('AUTH0_CLIENT_ID')
    AUTH0_CLIENT_SECRET = env.str('AUTH0_CLIENT_SECRET')
    CDIP_API = env.str('CDIP_API')

oauth_token_url = f"https://{AUTH0_DOMAIN}/oauth/token"

def get_access_token():

    response = requests.post(oauth_token_url,
                             json={
                                 "client_id": AUTH0_CLIENT_ID,
                                 'client_secret': AUTH0_CLIENT_SECRET,
                                 'audience': AUTH0_API_AUDIENCE,
                                 'grant_type': 'client_credentials',
                                 'scope': 'write:position'
                             })

    if response.status_code == 200:
        return response.json()

    else:
        print(f'[{response.status_code}], {response.text}')


def execute(options):

    token = get_access_token()
    if not token:
        print('Cannot get a valid access_token.')

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}"
    }

    for x in range(options.maximum_iterations):
        tic = time.perf_counter()

        payload = [{
            "device_id": options.device_id,
            "recorded_at": datetime.now(tz=pytz.utc).isoformat(),
            "location": {"x": random.randint(-180, 180), "y": random.randint(-90, 90)},
            "integration_id": 1234
        } for _ in range(10)]

        resp = requests.post(f'{CDIP_API}/positions', headers=headers, json=payload)
        timing.append(time.perf_counter() - tic)

        if resp.status_code != 200:
            print(payload)
            print(f'sc: {resp.status_code}, {resp.text}')

    print(f'Max: {max(timing)}')
    print(f'Mean: {statistics.mean(timing)}')
    print(f'Stddev: {statistics.stdev(timing)}')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(allow_abbrev=True)
    parser.add_argument('--automatic', '-a',
                        action='store_true',
                        help='Run automatically or wait for input.',
                        default=False)

    parser.add_argument('--device_id', '-m',
                        action='store',
                        help='Device Id',
                        default='default')

    parser.add_argument('--max_iterations', '-i', action='store', type=int,
                        dest='maximum_iterations',
                        help='Maximum number of iterations. Helpful when running in automatic mode.',
                        default=5)

    parser.add_argument('--sleep_time', '-s', action='store',
                        help='Number of seconds to wait between automatic iterations.', type=float,
                        default=2.0)

    options = parser.parse_args()
    execute(options)
