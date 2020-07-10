import json
import itertools

import requests
from airflow.hooks.base_hook import BaseHook
from airflow.models import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.dagrun_operator import TriggerDagRunOperator
from airflow.utils.dates import days_ago
from walrus import Database

from utils import send_to_destination, transform_records, to_er_observation
from cdip_http_hook import CdipHttpHook

args = {
    'owner': 'Airflow',
    'start_date': days_ago(2),
}

INBOUND_UNPROCESSED = 'inbound-unprocessed'
TRANSFORMED_TO_CDIP = 'transformed-to-cdip'
READY_TO_GO = 'ready-to-go'
READ_BATCH_SIZE = 5
LAST_ID_UNPROCESSED = 'last-id-unprocessed'
LAST_ID_TRANSFORMED = 'last-id-transformed'
LAST_ID_READY = 'last-id-ready'


# the fetch_* tasks get things going. external invocations could also startup DAGs and pass in data.
def fetch_collarids_from_savannah(*args, **context):
    print('fetch_collarids_from_savannah entered')

    # this info will come from cdip admin api in an integrated system
    connection = BaseHook.get_connection("savannah_api")

    # fetch using CdipHttpHook
    http_hook = CdipHttpHook(connection.host)
    response = http_hook.run(endpoint='savannah_data/data_auth',
                             data={
                                 'request': 'authenticate',
                                 'uid': connection.login,
                                 'pwd': connection.password
                             })
    if response.status_code == 200:

        auth_result = json.loads(response.text)

        if auth_result.get('sucess'):
            collar_ids = auth_result['records']
            return collar_ids
        else:
            print(f"Login wasn't successful. {auth_result['login_error_msg']}")
    else:
        print(f'Failed to authenticate\nStatus Code: {response.status_code}\n{response.text}')


def fetch_collars(**context):
    print('fetch_collars entered')
    collar_ids = context['task_instance'].xcom_pull(task_ids='fetch_collarids_from_savannah')
    print(f'== {len(collar_ids)} collars received ==')

    connection = BaseHook.get_connection("savannah_api")

    # fetch using CdipHttpHook
    http_hook = CdipHttpHook(connection.host)

    # fetch data for each collar and accumulate in a list

    # records_by_collar_id = {}
    for collar_id in collar_ids:
        print(f'Fetching for collar: {collar_id}')
        # print(f'Fetching a batch for collar: {collar_id} with record_index={highest_known_index}')
        response = http_hook.run(endpoint='savannah_data/data_request',
                                 data={
                                     'request': 'data_download',
                                     'uid': connection.login,
                                     'pwd': connection.password,
                                     'collar': collar_id,
                                     'record_index': -1 # TODO: need to store & reuse cursor.
                                 })

        if response.status_code == 200:

            result = json.loads(response.text)

            if result and result['records']:

                redis = _get_redis_connection()
                unprocessed_stream = redis.Stream(INBOUND_UNPROCESSED)
                if len(result['records']) > 10:
                    result['records'] = result['records'][:10]
                # records_by_collar_id[collar_id] = result['records']

                # TODO: maybe flatten list to add individual observations to stream?
                msg_id = unprocessed_stream.add({
                    'type': 'savannah',  # TODO: metadata to help downstream tasks.
                    'data': json.dumps(result['records'])
                })
                print(f'added to stream {msg_id}')
        else:
            raise Exception(f'Something went wrong, response is : {response.status_code}, {response.text}')


def transform_savannah_to_cdip(**context):
    print('transform_savannah_to_cdip entered')

    redis = _get_redis_connection()
    unprocessed_stream = redis.Stream(INBOUND_UNPROCESSED)
    transformed_stream = redis.Stream(TRANSFORMED_TO_CDIP)

    # get/initialize the unprocessed last_id
    last_id_unprocessed = redis.get(LAST_ID_UNPROCESSED)
    if not last_id_unprocessed:
        redis.set(LAST_ID_UNPROCESSED, 0)

    # TODO: read in batches rather than reading everything new since last_id
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


# this is currently not doing much, more of a placeholder task
# to read standardized data and prepare to send to a destination
def prepare_to_send(**context):
    print('prepare_to_send entered')

    redis = _get_redis_connection()
    transformed_stream = redis.Stream(TRANSFORMED_TO_CDIP)
    ready_stream = redis.Stream(READY_TO_GO)

    last_id_transformed = redis.get(LAST_ID_TRANSFORMED)
    if not last_id_transformed:
        redis.set(LAST_ID_TRANSFORMED, 0)

    transformed_records = transformed_stream.read(last_id=last_id_transformed)
    if transformed_records:
        [
            ready_stream.add({
                'data': json.dumps(json.loads(r[1][b'data']))
            }) for r in transformed_records
        ]
        # finally update LAST_ID_TRANSFORMED
        redis.set(LAST_ID_TRANSFORMED, transformed_records[-1][0])


def post_to_destination(**context):
    print('post_to_destination entered')

    redis = _get_redis_connection()
    ready_stream = redis.Stream(READY_TO_GO)

    last_id_ready = redis.get(LAST_ID_READY)
    if not last_id_ready:
        redis.set(LAST_ID_READY, 0)

    ready_records = ready_stream.read(last_id=0)
    if ready_records:
        to_send_list = [json.loads(r[1][b'data']) for r in ready_records]

        print('========POSTING records=========')
        print(f'{len(to_send_list)} recs')

        dest_host, dest_auth_token = _get_dest_connection()
        send_to_destination(to_send_list, destination_host=dest_host, destination_auth_token=dest_auth_token)
        # finally update LAST_ID_READY
        redis.set(LAST_ID_READY, ready_records[-1][0])


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

with DAG(
        dag_id='Savannah-streams',
        default_args=args,
        schedule_interval=None,
        tags=['savannah_client']
) as dag:
    fetch_collarids_from_savannah_task = PythonOperator(
        task_id='fetch_collarids_from_savannah',
        provide_context=True,
        python_callable=fetch_collarids_from_savannah
    )

    fetch_collars_task = PythonOperator(
        task_id='fetch_collars',
        provide_context=True,
        python_callable=fetch_collars
    )

    transform_savannah_to_cdip_task = PythonOperator(
        task_id='transform_savannah_to_cdip',
        provide_context=True,
        python_callable=transform_savannah_to_cdip,
    )

    prepare_to_send_task = PythonOperator(
        task_id='prepare_to_send',
        provide_context=True,
        python_callable=prepare_to_send,
    )

    post_to_destination_task = PythonOperator(
        task_id='post_to_destination',
        provide_context=True,
        python_callable=post_to_destination,
    )

    # trigger_next = TriggerDagRunOperator(
    #     task_id='trigger_next',
    #     trigger_dag_id='To-destination'
    # )

    fetch_collarids_from_savannah_task \
    >> fetch_collars_task \
    >> transform_savannah_to_cdip_task \
    >> prepare_to_send_task \
    >> post_to_destination_task
