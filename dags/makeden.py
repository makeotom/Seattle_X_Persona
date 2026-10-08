'''
Makeo and Eden's pipeline
Sep 20th (11 months!)
9-20-26

ELT pipeline:
extract raw requests,
load request in object storage
transform raw request into Relational Data Base
'''

from pendulum import datetime
from airflow.sdk import dag, task, Variable

from transformations.load_static import extract_transform_load_raw

@dag(
    schedule='@daily',
    start_date=datetime(2015, 1, 1, tz='America/Los_Angeles'),
    catchup=False,
    tags=['seattle_x_persona', 'ml-ops', 'data-ops']
)
def elt_oba_static_schedule():
    '''
    ELT pipeline:
    extract raw requests,
    load request in object storage
    transform raw request into Relational Data Base
    '''

    @task()
    def extract_transform_load_raw_oba():
        '''
        ### Extract raw data and Load into storage
        '''
        routes = [Variable.get('example_route', default=True)]
        api_key = Variable.get('oba_api_key', default=True)
        bronze_url = Variable.get('bronze_url', default=True)
        use_example_route = Variable.get('use_example_route', default=True)
        if use_example_route:
            routes = False
        extract_transform_load_raw(routes=routes, api_key=api_key, bronze_url=bronze_url)

    extract_transform_load_raw_oba()


elt_oba_static_schedule()