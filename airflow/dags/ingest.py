from datetime import datetime, timezone
from airflow.models import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.dagrun_operator import TriggerDagRunOperator
from airflow.hooks.base_hook import BaseHook

from walrus import Database, Stream

INGEST_STREAM = 'transformed-to-cdip'
INGEST_CONSUMER_GROUP = 'ingest-consumers'
TEST_DEST_STREAM = 'test-destination-stream'

default_args = {
    'owner': 'Airflow',
    'start_date': datetime.now(tz=timezone.utc)
}

# this reads from ingest stream, writes to the destination stream and triggers dispatch dag


def ingest_data(**context):
    redis = _get_redis_connection()

    ingest_group = redis.time_series(INGEST_CONSUMER_GROUP, INGEST_STREAM)
    ingest_group.create()  # creates a new time series only if it doesn't exist

    dest_stream = redis.Stream(TEST_DEST_STREAM)

    new_messages = ingest_group.read()
    print(f'read {len(new_messages)} from ingest stream')
    print(f'{new_messages[:3]}')
    [
        dest_stream.add(m.data) for m in new_messages
    ]
    acked_cnt = None
    if new_messages:
        acked_cnt = ingest_group.transformed_to_cdip.ack(*new_messages)

    print(f'ingest_task returning. acked_cnt: {acked_cnt}')


def _get_redis_connection():
    redis_config = BaseHook.get_connection("redis_connection")

    return Database(
        host=redis_config.host,
        port=redis_config.port,
        password=redis_config.password
    )

    # this info will come from cdip admin api in an integrated system


def _get_dest_connection():
    config = BaseHook.get_connection('cdip_destination')
    return config.host, config.password


with DAG(dag_id='ingest-dag',
         default_args=default_args,
         schedule_interval=None) as dag:
    ingest_task = PythonOperator(task_id='ingest-task',
                                 provide_context=True,
                                 python_callable=ingest_data)

    trigger_next = TriggerDagRunOperator(
        task_id='trigger_next',
        trigger_dag_id='To-destination'
    )

    ingest_task >> trigger_next

