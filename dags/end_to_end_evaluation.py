""" THIS IS A NICE PLACEHOLDER BUT WE NEED TO ADD SOME BEST PRACTICES FOR AIRFLOW
crucial concpet: TASKS MUST BE IDEMPOTENT
1. WE NEED TO USE DAG DECORATOR FORMAT
2. WE NEED TO ADD TASK IDS
3. ADD DESCRIPTIOSN TO DAG
4. USE COHERENT DAGS
5. ITS GOOD TO KEEP THE DEFAULT ARGS
6. DAGRUN_TIMEOUT
7. max_consecutive_failed_dag_runs




"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.models import Variable
import os

def get_config_values():
    """Get configuration values from Airflow Variables and environment"""
    # Use GitSync mounted path (subPath = "dags" mounts to /opt/airflow/dags/repo/)
    dag_repo_path = "/opt/airflow/dags/repo"
    
    return {
        'test_cases_file': Variable.get("end_to_end_test_cases_file", 
                                       default_var=f"{dag_repo_path}/end-to-end/test_cases.json"),
        'websocket_host': Variable.get("websocket_host", default_var="localhost"),
        'websocket_port': int(Variable.get("websocket_port", default_var="9999")),
        'websocket_endpoint_id': Variable.get("websocket_endpoint_id", default_var="default"),
        'evaluation_model': Variable.get("evaluation_model", default_var="gpt-4.1-mini"),
        'openai_api_token': os.getenv('OPENAI_API_TOKEN'),
        'autoptic_api_token': os.getenv('AUTOPTIC_API_TOKEN'),
        'dag_repo_path': dag_repo_path,  # For accessing end-to-end scripts
    }

def placeholder_task(**context):
    """Placeholder function for tasks not yet implemented"""
    task_id = context['task_instance'].task_id
    config = get_config_values()
    print(f"[{task_id}] Placeholder task executed successfully")
    print(f"[{task_id}] Config: {config}")
    return f"{task_id}_completed"

with DAG(
    dag_id="end_to_end_evaluation",
    description="End-to-end evaluation pipeline for PQL queries and analysis",
    start_date=datetime(2025, 1, 1),
    schedule_interval="@once",  # Run once on deployment
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "autoptic",
        "depends_on_past": False,
        "email_on_failure": True,
        "email_on_retry": False,
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["evaluation", "pql", "end-to-end"],
) as dag:
    
    # Task 0: Install Python dependencies
    install_dependencies = BashOperator(
        task_id="install_dependencies",
        bash_command="""
        pip install --user deepeval websockets pandas transformers torch
        echo "Dependencies installed successfully"
        """,
        retries=2,
        execution_timeout=timedelta(minutes=10),
    )
    
    # Task 1: Check all service dependencies
    check_dependencies = PythonOperator(
        task_id="check_dependencies", 
        python_callable=placeholder_task,
        retries=3,
        retry_delay=timedelta(minutes=1),
        execution_timeout=timedelta(minutes=5),
    )
    
    # Task 2: Validate test cases
    validate_test_cases = PythonOperator(
        task_id="validate_test_cases",
        python_callable=placeholder_task,
        retries=2,
    )
    
    # Task 3: Run WebSocket tests
    run_websocket_tests = PythonOperator(
        task_id="run_websocket_tests",
        python_callable=placeholder_task,
        retries=2,
        execution_timeout=timedelta(minutes=10),
    )
    
    # Task 4: Evaluate PQL quality
    evaluate_pql_quality = PythonOperator(
        task_id="evaluate_pql_quality",
        python_callable=placeholder_task,
        retries=1,
    )
    
    # Task 5: Evaluate analysis quality  
    evaluate_analysis_quality = PythonOperator(
        task_id="evaluate_analysis_quality",
        python_callable=placeholder_task,
        retries=1,
    )
    
    # Task 6: Generate evaluation report
    generate_evaluation_report = PythonOperator(
        task_id="generate_evaluation_report",
        python_callable=placeholder_task,
    )
    
    # Task 7: Cleanup old runs
    cleanup_old_runs = BashOperator(
        task_id="cleanup_old_runs",
        bash_command="echo 'Cleanup placeholder - would remove old run directories'",
    )
    
    # Task 8: Notify results
    notify_results = PythonOperator(
        task_id="notify_results",
        python_callable=placeholder_task,
        trigger_rule="all_done",  # Run even if some tasks fail
    )
    
    # Define task dependencies
    install_dependencies >> check_dependencies >> validate_test_cases >> run_websocket_tests
    run_websocket_tests >> [evaluate_pql_quality, evaluate_analysis_quality]
    [evaluate_pql_quality, evaluate_analysis_quality] >> generate_evaluation_report
    generate_evaluation_report >> cleanup_old_runs >> notify_results