from pprint import pprint

from airflow.utils.dates import days_ago

from airflow.models import DAG
from airflow.operators.python_operator import PythonOperator


"""
An example of invoking a DAG remotely over Airflow's REST API (using an HTTP POST).
Additional data can be passed in to the DAG by including a JSON in the POST body. 
The json should have a key called conf. The can be an arbitrary json object. 

couple ways to invoke this dag:
1) curl
curl -X POST http://localhost:8080/api/experimental/dags/push-handler/dag_runs \
-H 'Content-Type: application/json'  -d '{"conf":"{\"key\":\"blah\"}"}'

2) python code using requests lib:

AIRFLOW_REST_ENDPOINT = 'http://localhost:8080/api/experimental/dags'
DAG_ID = 'push-handler'

url = '/'.join((AIRFLOW_REST_ENDPOINT,
              DAG_ID,
              'dag_runs')) 
              
data = {
    'conf' : {
        'key1': 'val1',
        'id': 'an_id',
        'dest': 'http://nowhere.com'
    }
}

requests.post(url=url, json=data)
"""

args = {
    'owner': 'Airflow',
    'start_date': days_ago(2),
}

dag = DAG(
    dag_id='push-handler',
    default_args=args,
    schedule_interval=None,
    tags=['push-handler']
)


def push_handler(**context):
    print('push_handler task entered')
    pprint(context)
    print('print dag_run')
    # retrieve the conf object passed in by the invoker
    received_conf: dict = context["dag_run"].conf
    print(f'dag_run.conf: {received_conf}')

    for k, v in received_conf.items():
        print(f'key: {k}, val: {v}')

    return 'push_handler task returns'


run_this = PythonOperator(
    task_id='push-handler-task',
    provide_context=True,
    python_callable=push_handler,
    dag=dag,
)
