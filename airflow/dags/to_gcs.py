import logging
import datetime

from airflow.utils.dates import days_ago

from airflow.operators.python_operator import PythonOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.contrib.hooks.gcs_hook import GoogleCloudStorageHook

from airflow.models import DAG

"""
this dag uses the GoogleCloudStorageHook to upload a local file to GCS
"""

bucket_name = 'test-bucket-rohitc-vulcan-er'
local_file_path = '/Users/rohitc/package-lock.json'


def create_bucket():
    gcs_hook = GoogleCloudStorageHook(google_cloud_storage_conn_id='google_cloud_default')
    bucket_id = gcs_hook.create_bucket(bucket_name=bucket_name,
                           project_id='aws-aws-link-for-cl-1588789001')
    print(f'created bucket {bucket_id}')
    return bucket_id


def upload_file():
    gcs_hook = GoogleCloudStorageHook()  # will use the default value for google_cloud_storage_conn_id
    gcs_hook.upload(bucket=bucket_name,
                    object=f'package-lock-{datetime.datetime.now().timestamp()}.json',
                    filename=local_file_path,
                    mime_type='application/json')

    print('uploaded file')


default_args = {
    'owner': 'Airflow',
    'start_date': days_ago(1),
}

with DAG(
    dag_id='to-gcs',
    schedule_interval=None,
    default_args=default_args
) as dag:
    dummy_task = DummyOperator(task_id='dummy-task')
    # create_bucket = PythonOperator(task_id='create_bucket',
    #                                python_callable=create_bucket)
    upload_file = PythonOperator(task_id='upload-file',
                                 python_callable=upload_file)


