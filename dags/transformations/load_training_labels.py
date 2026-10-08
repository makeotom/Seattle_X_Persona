'''
Makeo Tom
9-05-26
load schedule and buildtraining data into csv files overtime
responsible for creating a schedule to load all csv data and save the resuts as training data
'''
from onebusaway import OnebusawaySDK
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

def extract_labels(sub_df: pd.DataFrame, n=24, client=OnebusawaySDK()):
    '''
    extract all training labels for the last n hours
    '''
    stop_id = sub_df.name
    try:
        res = client.arrival_and_departure.list(stop_id=stop_id, minutes_before=60 * n, minutes_after=0)

        arrivals_df = pd.json_normalize(res.data.entry.to_dict()['arrivalsAndDepartures'])
        arrivals_df = arrivals_df[['tripId', 'scheduledDepartureTime', 'routeId', 'predicted', 'predictedDepartureTime', 'lastUpdateTime']]
        arrivals_df = arrivals_df.rename(columns={'tripId': 'ride_id', 'scheduledDepartureTime':'departure_time', 'routeId': 'route_id', 'predictedDepartureTime':'actual_departure_time', 'lastUpdateTime': 'last_update_time'})

        # select and build features
        arrivals_df['departure_time'] = pd.to_datetime(arrivals_df['departure_time'], unit='ms', utc=True).dt.tz_convert('America/Los_Angeles').dt.tz_localize(None)
        arrivals_df['actual_departure_time'] = pd.to_datetime(arrivals_df['actual_departure_time'], unit='ms', utc=True).dt.tz_convert('America/Los_Angeles').dt.tz_localize(None)
        arrivals_df['last_update_time'] = pd.to_datetime(arrivals_df['last_update_time'], unit='ms', utc=True).dt.tz_convert('America/Los_Angeles').dt.tz_localize(None)
        sub_df = pd.merge(sub_df, arrivals_df, how='left', on=['ride_id', 'departure_time', 'route_id'])

        sub_df = sub_df[sub_df['predicted'] & (sub_df['last_update_time'] > sub_df['actual_departure_time'])]
        return sub_df
    except Exception as e:
        print('>failed request')

    return pd.DataFrame()
    

def get_training_labels(silver_url: str, oba_api_key: str) -> pd.DataFrame:
    '''
    join the matching labels to the arrival status dataframe
    '''
    hrs = 24
    minutes = 0
    client = OnebusawaySDK(api_key=oba_api_key)
    arrival_status_df = pd.read_csv(f'{silver_url}/training_features.csv', parse_dates=['current_time', 'departure_time'])
    arrival_status_df = arrival_status_df.groupby('stop_id').apply(extract_labels, n=hrs, client=client)
    arrival_status_df['trip_time'] = arrival_status_df['actual_departure_time'] - arrival_status_df['current_time'] # minutes till arrival
    arrival_status_df = arrival_status_df[arrival_status_df['trip_time'] > pd.Timedelta(minutes=0)]
    arrival_status_df['trip_time'] = arrival_status_df['trip_time'].dt.seconds
    # arrival_status_df = arrival_status_df[['route_id', 'stop_seq', 'day_type', 'rush_hour_status', 'far_status', 'distance', 'trip_time', 'actual_departure_time', 'current_time']]
    arrival_status_df = arrival_status_df[['route_id', 'stop_seq', 'day_type', 'rush_hour_status', 'far_status', 'distance', 'trip_time']]
    arrival_status_df = arrival_status_df.reset_index(drop=True)
    return arrival_status_df


def load_training_labels(silver_url: str, gold_url: str, oba_api_key: str):
    new_df = get_training_labels(silver_url=silver_url, oba_api_key=oba_api_key)
    try:
        old_df = pd.read_csv(f'{gold_url}/training.csv')
        # old_df = old_df[['route_id', 'stop_seq', 'day_type', 'rush_hour_status', 'far_status', 'distance', 'trip_time', 'actual_departure_time', 'current_time']]
        old_df = old_df[['route_id', 'stop_seq', 'day_type', 'rush_hour_status', 'far_status', 'distance', 'trip_time']]
        old_df = old_df.reset_index(drop=True)
        new_df = pd.concat([old_df, new_df], ignore_index=True)
        new_df = new_df.drop_duplicates()
    except Exception as e:
        ''

    new_df.to_csv(f'{gold_url}/training.csv', index=False)