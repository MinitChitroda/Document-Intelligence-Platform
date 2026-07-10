from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'nightly_batch_dag',
    default_args=default_args,
    description='Runs PySpark batch reprocessing job nightly',
    schedule_interval='@daily',
    catchup=False,
) as dag:

    run_spark_job = BashOperator(
        task_id='run_spark_reprocessing',
        # Executes the PySpark job script in local mode inside the container
        bash_command='python /opt/airflow/dags/ddp/batch/spark_reprocessing_job.py'
    )
