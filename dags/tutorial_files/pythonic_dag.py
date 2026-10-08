import json
import pendulum
from airflow.sdk import dag, task

@dag(
    schedule=None,
    start_date=pendulum.datetime(2015, 1, 1),
    catchup=False,
    tags=['learning']
)
def pythonic_dag():
    '''
    hello documentation
    *bold stuff*
    '''

    @task()
    def extract():
        return 's3://extract'

    @task()
    def transform(ex_url):
        return 's3://loaded/storae'

    @task()
    def load(tr_url):
        return 's3://pretty_data'

    raw = extract()
    clean = transform(raw)
    store = load(clean)
        
pythonic_dag()