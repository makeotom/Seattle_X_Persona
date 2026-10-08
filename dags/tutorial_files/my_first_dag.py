'''
Makeo Tom
my first dag in airflow!
sep-17-26
'''

import textwrap
from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

# first dag
with DAG(
    'my_first_dag',
    default_args={
        'depends_on_past': False,
        'retries': 1,
        'retry_delay': timedelta(minutes=5)
    },
    description='makeo\'s first ever dag',
    schedule=timedelta(days=1),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['learning']
) as dag:

    # defining tasks
    task1 = BashOperator(
        task_id='print_date',
        bash_command='date'
    )
    task2 = BashOperator(
        task_id='say_bye',
        bash_command='echo "goodbye"',
        retry_delay=timedelta(minutes=1)
    )

    # writing documentation xd
    dag.doc_md = textwrap.dedent(
        '''
        #### task 1 -> **print the date**
        this task prints the current date that the task was executed on
        '''
    )

    task1.doc_md = textwrap.dedent(
        '''
        #### task 1 -> **print the date**
        this task prints the current date that the task was executed on
        '''
    )
    task2.doc_md = textwrap.dedent(
        '''
        #### task 2 -> **print goodbye**
        this task says goodbye
        '''
    )

    # create the dag xd
    task1 >> task2

