import json
from datetime import datetime, timezone

from airflow.models import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.utils.dates import days_ago

from walrus import Database

from utils import send_to_destination

TRANSFORMED_TO_CDIP = 'transformed-to-cdip'
READ_BATCH_SIZE = 5
LAST_ID_TRANSFORMED = 'last-id-transformed'

default_args = {
    'owner': 'Airflow',
    'start_date': datetime.now(tz=timezone.utc)
}


def post_to_destination(**context):
    print('post_to_destination entered')

    redis = Database()
    transformed_stream = redis.Stream(TRANSFORMED_TO_CDIP)

    last_id_transformed = redis.get(LAST_ID_TRANSFORMED)
    if not last_id_transformed:
        redis.set(LAST_ID_TRANSFORMED, 0)

    transformed_records = transformed_stream.read(last_id=0)
    if transformed_records:
        to_send_list = [json.loads(r[1][b'data']) for r in transformed_records]

        print('========POSTING records=========')
        print(f'{len(to_send_list)} recs')

        send_to_destination(to_send_list)
        # finally update LAST_ID_TRANSFORMED
        redis.set(LAST_ID_TRANSFORMED, transformed_records[-1][0])


with DAG(
    dag_id='To-destination',
    default_args=default_args,
    schedule_interval=None
) as dag:
    task = PythonOperator(
        task_id='post-to-destination',
        provide_context=True,
        python_callable=post_to_destination
    )