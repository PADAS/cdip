from datetime import timedelta
from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.operators.python_operator import PythonOperator
from airflow.utils.dates import days_ago
import requests

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': days_ago(21),
    'email': ['chrisdo@vulcan.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'everyday',
    catchup=True,
    default_args=default_args,
    description='Ping my site.',
    schedule_interval='@daily',
) as dag:


    def pinger(date_value):
        requests.get('https://heyeverybody.net', params={'datval': date_value})
    
    my_task = PythonOperator(
        task_id='pingmysite',
        python_callable=pinger,
        op_kwargs={
            'date_value': '{{ ds }}'
        }
    )
    
