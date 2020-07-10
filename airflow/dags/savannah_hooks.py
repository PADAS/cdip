import json

import requests
from airflow.hooks.base_hook import BaseHook
from airflow.models import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.utils.dates import days_ago

from utils import send_to_destination, transform_records
from cdip_http_hook import CdipHttpHook


"""
Another version of savannah integration. this fetches data from savannah using the CdipHttpHook. 
Airflow's HttpHook is easily swapped out with CdipHttpHook.
this code below configures CdipHttpHook by reading savannah config from Airflow's connection model.
non-demo code will fetch this config from CDIP admin.
"""

args = {
    'owner': 'Airflow',
    'start_date': days_ago(2),
}


def fetch_collarids_from_savannah(*args, **context):
    print('fetch_collarids_from_savannah entered')
    connection = BaseHook.get_connection("savannah_api")

    # http_hook = HttpHook(http_conn_id='savannah_api')

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

            # print('== Collar list ==')
            # [print(x) for x in collar_ids]
            return collar_ids
        else:
            print(f"Login wasn't successful. {auth_result['login_error_msg']}")
            # return 'Login failed'
    else:
        print(f'Failed to authenticate\nStatus Code: {response.status_code}\n{response.text}')
        # return 'Failed authentication'


def fetch_collars(**context):
    print('fetch_collars entered')
    collar_ids = context['task_instance'].xcom_pull(task_ids='fetch_collarids_from_savannah')
    print(f'== {len(collar_ids)} collars received ==')

    connection = BaseHook.get_connection("savannah_api")
    # http_hook = HttpHook(http_conn_id='savannah_api')

    # fetch using CdipHttpHook
    http_hook = CdipHttpHook(connection.host)

    # fetch data for each collar and accumulate in a list

    records_by_collar_id = {}
    for collar_id in collar_ids:
        print(f'Fetching for collar: {collar_id}')
        # print(f'Fetching a batch for collar: {collar_id} with record_index={highest_known_index}')
        response = http_hook.run(endpoint='savannah_data/data_request',
                                 data={
                                     'request': 'data_download',
                                     'uid': connection.login,
                                     'pwd': connection.password,
                                     'collar': collar_id,
                                     'record_index': -1
                                 })

        if response.status_code == 200:

            result = json.loads(response.text)

            if result and result['records']:
                if len(result['records']) > 10:
                    result['records'] = result['records'][:10]
                records_by_collar_id[collar_id] = result['records']

        else:
            raise Exception(f'Something went wrong, response is : {response.status_code}, {response.text}')

    return records_by_collar_id


def transform_savannah_to_cdip(*args, **context):
    print('transform_savannah_to_cdip entered')
    records_to_transform = context['task_instance'].xcom_pull(task_ids='fetch_collars')
    print(f'{len(records_to_transform)} records to transform')
    transformed_records = []
    for collar, records in records_to_transform.items():
        transformed_records += transform_records(collar, records)
    # transformed_records = [to_er_observation(collar, records) for collar, records in records_to_transform.items()]
    return transformed_records


def post_to_destination(*args, **context):
    print('post_to_destination entered')
    records_to_post = context['task_instance'].xcom_pull(task_ids='transform_savannah_to_cdip')
    print('========POSTING records=========')
    print(f'{len(records_to_post)} recs')

    send_to_destination(records_to_post)


dag = DAG(
    dag_id='Savannah-DAG-hooks',
    default_args=args,
    schedule_interval=None,
    tags=['savannah_client']
)


fetch_collarids_from_savannah_task = PythonOperator(
    task_id='fetch_collarids_from_savannah',
    provide_context=True,
    python_callable=fetch_collarids_from_savannah,
    dag=dag,
)

fetch_collars_task = PythonOperator(
    task_id='fetch_collars',
    provide_context=True,
    python_callable=fetch_collars,
    dag=dag
)

transform_savannah_to_cdip_task = PythonOperator(
    task_id='transform_savannah_to_cdip',
    provide_context=True,
    python_callable=transform_savannah_to_cdip,
    dag=dag,
)

# post_to_destination_task = PythonOperator(
#     task_id='post_to_destination',
#     provide_context=True,
#     python_callable=post_to_destination,
#     dag=dag,
# )

fetch_collarids_from_savannah_task >> fetch_collars_task >> transform_savannah_to_cdip_task
# >> post_to_destination_task


