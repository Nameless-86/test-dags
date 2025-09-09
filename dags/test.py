from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
	dag_id="test",
	start_date=datetime(2025, 1, 1),
	schedule_interval=None,
	catchup=False,
	default_args={
		"owner": "test",
		"depends_on_past": False,
		"email_on_failure": False,
		"email_on_retry": False,
		"retries": 1,
		"retry_delay": timedelta(minutes=5),
	},
) as dag:
	BashOperator(task_id="say_hi", bash_command="echo 'Hello from gitsync!'")
