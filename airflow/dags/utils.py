from dateutil.parser import parse as parse_date
import pytz
from typing import NamedTuple
from datetime import datetime
import requests

from airflow.exceptions import AirflowException

cursors = {}


class ApiDetails(NamedTuple):
    username: str
    password: str
    api_root: str = 'https://api.savannahtracking.co.ke'


class ERObservation(NamedTuple):
    manufacturer_id: str
    recorded_at: datetime
    location: dict
    subject_name: str
    additional: dict

    def to_dict(self):
        return self._asdict()


def transform_records(collar_id, records):
    return [to_er_observation(collar_id, r) for r in records]


"""
{'record_index': 30263912, 
'record_time': '6/10/2020 4:00:12 PM', 
'time_to_fix': 0, 
'latitude': -2.059603, 
'longitude': 34.37017, 
'hdop': 0, 
'h_accuracy': 0, 
'heading': 0, 
'speed': 0, 
'speed_accuracy': 0, 
'altitude': 0, 
'temperature': 23.4, 
'initial_data': '', 
'battery': 3.68}
"""

def to_er_observation(collar_id, r):
    return ERObservation(
        manufacturer_id=collar_id,
        subject_name=collar_id,
        location={'lat': r['latitude'], 'lon': r['longitude']},
        recorded_at=parse_date(r['record_time']).replace(tzinfo=pytz.utc).isoformat(),
        additional={
            'record_index': r.get('record_index'),
            'time_to_fix': r.get('time_to_fix'),
            'hdop': r.get('hdop'),
            'h_accuracy': r.get('h_accuracy'),
            'heading': r.get('heading'),
            'speed': r.get('speed'),
            'speed_accuracy': r.get('speed_accuracy'),
            'altitude': r.get('altitude'),
            'temperature': r.get('temperature'),
            'initial_data': r.get('initial_data'),
            'battery': r.get('battery')
        }
    ).to_dict()


ER_API_BASE = 'https://dev.pamdas.org/api/v1.0'
ER_API_AUTH_TOKEN = 'blah'


def send_to_destination(observations, destination_host=ER_API_BASE, destination_auth_token=ER_API_AUTH_TOKEN):
    if observations:
        url = '/'.join((destination_host,
                        'sensors',
                        'generic',
                        'savannah-airflow',
                        'status'))
        print(f'posting {len(observations)} observations to: {url}')

        def generate_observation_batches(batch_size=256):
            num_obs = len(observations)
            for start_index in range(0, num_obs, batch_size):
                yield observations[
                      start_index: min(start_index + batch_size, num_obs)]

        for batch in generate_observation_batches():
            try:
                response = requests.post(url,
                                         json=batch,
                                         headers={
                                             'Authorization': f'Bearer {destination_auth_token}'})
                print(f'{response.text} {response.status_code}')
            except Exception as ex:
                print(
                    f'Exception occurred while posting to destination DAS: {ex}')
                raise AirflowException(f'Exception occurred while posting to destination DAS: {ex}')
    else:
        print('Observations empty, nothing to post')


# def get_cursor_value(collar_id):
#     if collar_id in cursors:
#         return cursors[collar_id]
#     return 0
#
#
# def set_cursor_value(collar_id, val):
#     cursors[collar_id] = val
