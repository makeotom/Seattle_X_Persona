from pendulum import datetime
from datetime import timedelta
from airflow.providers.standard.sensors.external_task import ExternalTaskSensor
from airflow.sdk import dag, task, Variable

from transformations.load_check_schedule import load_check_schedule
from transformations.load_training_features import incrementally_load_training_features

@dag(
    schedule='4 0 * * *',
    start_date=datetime(2015, 1, 1, tz='America/Los_Angeles'),
    catchup=False,
    tags=['seattle_x_persona', 'ml-ops', 'data-ops'],
)
def etl_training_features():

    # wait_for_makeden = ExternalTaskSensor(
    #     task_id='wait_for_static_schedule',
    #     external_dag_id='elt_oba_static_schedule',
    #     external_task_id='extract_transform_load_raw_oba',
    #     allowed_states=['success', 'skipped'],
    #     failed_states=['failed'],
    #     mode='poke',
    #     poke_interval=60,
    #     timeout=60,
    #     execution_delta=timedelta(seconds=60)
    # )
    
    @task()
    def extract_transform_load_schedule_data():
        '''
        load the check schedule
        '''
        silver_url = Variable.get('silver_url', default=True)
        bronze_url = Variable.get('bronze_url', default=True)
        oba_api_key = Variable.get('oba_api_key', default=True)

        return load_check_schedule(silver_url=silver_url, bronze_url=bronze_url, oba_api_key=oba_api_key)

    @task()
    def load_training_features(system_check_schedule_url):
        '''
        this task should be dynamically created for each check group
        using the given parameters then build the training features
        '''
        # TODO write a while loop that checks (minute-ly accuracy) if the current time matches a system check time-> if it matches call function to load the training features given the time
        # send data down kafak stream and subscribe to data i the 
        # TODO test this task's functionality
        silver_url = Variable.get('silver_url', default=True)
        bronze_url = Variable.get('bronze_url', default=True)
        oba_api_key = Variable.get('oba_api_key', default=True)
        incrementally_load_training_features(silver_url=silver_url, bronze_url=bronze_url, oba_api_key=oba_api_key)

    url = extract_transform_load_schedule_data()
    # wait_for_makeden >> url
    load_training_features(url)

etl_training_features()