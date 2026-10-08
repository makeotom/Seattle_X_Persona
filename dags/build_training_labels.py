from pendulum import datetime
from datetime import timedelta
from airflow.providers.standard.sensors.external_task import ExternalTaskSensor
from airflow.sdk import dag, task, Variable

from transformations.load_training_labels import load_training_labels

@dag(
    schedule='55 * * * *',
    start_date=datetime(2015, 1, 1, tz='America/Los_Angeles'),
    catchup=False,
    tags=['seattle_x_persona', 'ml-ops', 'data-ops']
)
def etl_training_labels():

    @task()
    def extract_transform_load_training_labels():
        '''
        load the check schedule
        '''
        gold_url = Variable.get('gold_url', default=True)
        silver_url = Variable.get('silver_url', default=True)
        oba_api_key = Variable.get('oba_api_key', default=True)

        return load_training_labels(silver_url=silver_url, gold_url=gold_url, oba_api_key=oba_api_key)

    extract_transform_load_training_labels()

etl_training_labels()