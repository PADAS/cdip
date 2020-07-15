import time
from datetime import datetime, timedelta
import pytz
import json
import random
import requests
import statistics

timing = []

bearer_token = '<todo get token>'

headers = {
    "authorization": f"Bearer {bearer_token}"
}


def execute(options):
    for x in range(options.maximum_iterations):
        tic = time.perf_counter()

        payload = {
            "device_id": options.device_id,
            "recorded_at": datetime.now(tz=pytz.utc).isoformat(),
            "location": {"x": random.randint(-180, 180), "y": random.randint(-90, 90)}
        }
        resp = requests.post('http://localhost:9500/positions', headers=headers, json=payload)
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
                        default=1000)

    parser.add_argument('--sleep_time', '-s', action='store',
                        help='Number of seconds to wait between automatic iterations.', type=float,
                        default=2.0)

    options = parser.parse_args()
    execute(options)
