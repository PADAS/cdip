import json
import itertools

from airflow.models import DAG
from airflow.operators.dagrun_operator import TriggerDagRunOperator
from airflow.operators.python_operator import PythonOperator
from airflow.utils.dates import days_ago

from walrus import Database

from utils import to_er_observation

INBOUND_UNPROCESSED = 'inbound-unprocessed'
TRANSFORMED_TO_CDIP = 'transformed-to-cdip'

READ_BATCH_SIZE = 5
LAST_ID_UNPROCESSED = 'last-id-unprocessed'

default_args = {
    'owner': 'Airflow',
    'start_date': days_ago(2)
}


def transform_to_cdip(**context):
    print('transform_to_cdip entered')

    redis = Database()
    unprocessed_stream = redis.Stream(INBOUND_UNPROCESSED)
    transformed_stream = redis.Stream(TRANSFORMED_TO_CDIP)

    # get/initialize the unprocessed last_id
    last_id_unprocessed = redis.get(LAST_ID_UNPROCESSED)
    if not last_id_unprocessed:
        redis.set(LAST_ID_UNPROCESSED, 0)

    unprocessed_records = unprocessed_stream.read(last_id=last_id_unprocessed)
    # print(unprocessed_records)
    if unprocessed_records:
        # TODO see todo in the upstream task.
        unprocessed_json = [json.loads(r[1][b'data']) for r in unprocessed_records]
        unprocessed_json_items = list(itertools.chain.from_iterable(unprocessed_json))

        transformed_records = [to_er_observation('savannah-collar', r) for r in unprocessed_json_items]

        [transformed_stream.add({
            'data': json.dumps(r)
        }) for r in transformed_records]

        # msg_id = transformed_stream.add({
        #     'data': json.dumps(transformed_records)
        # })

        # finally update LAST_ID_UNPROCESSED
        redis.set(LAST_ID_UNPROCESSED, unprocessed_records[-1][0])


with DAG(
        dag_id='Transformer-dag',
        default_args=default_args,
        schedule_interval=None,
        tags=['Transformer-dag']
) as dag:
    transform_task = PythonOperator(
        task_id='transform_to_cdip',
        provide_context=True,
        python_callable=transform_to_cdip
    )

    # trigger = TriggerDagRunOperator(
    #     task_id='trigger_next',
    #     trigger_dag_id=''
    # )