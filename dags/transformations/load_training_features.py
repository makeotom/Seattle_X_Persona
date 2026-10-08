'''
Makeo Tom
8-5-26
build training data into csv files overtime
responsible for referencing the schedule to load all csv data and save the resuts as training data
'''

import os
from dotenv import load_dotenv
import onebusaway
from onebusaway import OnebusawaySDK
from sortedcontainers import SortedDict
import json
import pandas as pd
from pandas import DataFrame

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import time

def get_arrival_status(row: DataFrame, trip_df: DataFrame, client: OnebusawaySDK):
    '''
    given a check time for a stop, check it and build all the rows

    return:
    ['route_id', 'stop_id', 'ride_id', 'stop_seq', 'arrival_time', 'departure_time', 'distance', 'current_time', 'attempted_time']
    '''
    print(row)
    stop_id = row['stop_id']
    check_time = row['check_time']
    route_ids = row['route_ids'][1:-1].replace("'", '').split(', ')

    # determine the interval where we can find the targeted bus
    before = 10
    after = 10

    str_time = check_time.strftime("%Y-%m-%d_%H-%M-%S")
    # there will be some overlap (meaning you will find busses that have already been checked or should be chekd later but it just means more trianing data)
    res = client.arrival_and_departure.list(stop_id=stop_id, minutes_before=before, minutes_after=after, time=str_time)
    if res.code == 200:
        arrivals_json = res.data.entry.to_dict()['arrivalsAndDepartures']
        arrivals_df = pd.json_normalize(arrivals_json)

        if len(arrivals_df) > 0:
            arrivals_df = arrivals_df[(arrivals_df['routeId'].isin(route_ids)) & (arrivals_df['distanceFromStop'] > 0)]

            # get distance in meters of stop
            predicted_df = arrivals_df[arrivals_df['predicted']]

            # select important rows
            arrivals_df = arrivals_df[['routeId', 'stopId', 'tripId', 'stopSequence', 'scheduledArrivalTime', 'scheduledDepartureTime', 'distanceFromStop', 'lastUpdateTime']]
            arrivals_df = arrivals_df.rename(columns={'routeId':'route_id', 'stopId':'stop_id', 'tripId':'ride_id', 'stopSequence':'stop_seq', 'scheduledArrivalTime':'arrival_time', 'scheduledDepartureTime':'departure_time', 'distanceFromStop': 'distance', 'lastUpdateTime': 'current_time'})

            # filter to only choose realtime data
            arrivals_df = arrivals_df[arrivals_df['current_time'] > 0]

            # get the trip id then the average distance field
            
            res_trip_df = pd.json_normalize(res.data.references.to_dict()['trips'])[['id', 'directionId']]
            res_trip_df['directionId'] = pd.to_numeric(res_trip_df['directionId'], errors='coerce')
            arrivals_df = pd.merge(arrivals_df, res_trip_df, how='left', left_on='ride_id', right_on='id')
            arrivals_df = pd.merge(arrivals_df, trip_df[['route_id', 'trip_id', 'average_distance_between_stops']], left_on=['route_id', 'directionId'], right_on=['route_id', 'trip_id'])
            arrivals_df = arrivals_df.drop(columns=['directionId', 'id'])

            # convert timestamp to datetime
            arrivals_df['attempted_time'] = check_time
            arrivals_df['arrival_time'] = pd.to_datetime(arrivals_df['arrival_time'], unit='ms', utc='true').dt.tz_convert('America/Los_Angeles').dt.tz_localize(None)
            arrivals_df['departure_time'] = pd.to_datetime(arrivals_df['departure_time'], unit='ms', utc='true').dt.tz_convert('America/Los_Angeles').dt.tz_localize(None)
            arrivals_df['current_time'] = pd.to_datetime(arrivals_df['current_time'], unit='ms', utc='true').dt.tz_convert('America/Los_Angeles').dt.tz_localize(None)

        return arrivals_df

    return pd.DataFrame()

def load_arrival_status(check_df: DataFrame, system_check_df: DataFrame, rush_hour_intervals=[], oba_api_key: str=None, bronze_url: str=None):
    '''
    return -> ['route_id', 'stop_seq', 'day_type', 'rush_hour_status', 'far_status', 'distance', 'current_time']
    '''
    df = pd.merge(system_check_df, check_df, how='inner', on=['stop_id', 'system_check_time'])
    trip_df = pd.read_csv(f'{bronze_url}/trip.csv')

    client = OnebusawaySDK(api_key=oba_api_key)
    elm = [get_arrival_status(row, trip_df, client=client) for _, row in df.iterrows()]
    if len(elm) > 0:
        df = pd.concat(elm, ignore_index=True)
    else:
        return DataFrame()
    # (3) turn arrival status rows into real features
    # true -> weekday
    df['day_type'] = df['current_time'].dt.weekday <= 4  # (0->weekday 1->weekend)
    # true -> during rush hour
    df['rush_hour_status'] = ~((df['current_time'].dt.time.between(rush_hour_intervals[0], rush_hour_intervals[1])) & (df['current_time'].dt.time.between(rush_hour_intervals[2], rush_hour_intervals[3]))) # 0->not rush hour, 1->rush hour
    # true -> very far away
    df['far_status'] = (df['average_distance_between_stops'] / 2) < df['distance'].abs()

    return df[['route_id', 'stop_seq', 'day_type', 'rush_hour_status', 'far_status', 'distance', 'current_time', 'ride_id', 'stop_id', 'departure_time']]

def incrementally_load_training_features(silver_url: str, bronze_url: str, oba_api_key: str):
    '''
    over an extended period of time, load all training features
    '''
    import datetime

    # (1) load system_check_schedule (convert from datetime tin int time)
    system_check_df = pd.read_csv(f'{silver_url}/system_check_schedule.csv', parse_dates=['system_check_time'])

    # -> localize so to int makes it better
    localized_dt = system_check_df['system_check_time'].dt.tz_localize('America/Los_Angeles')
    system_check_df['check_time'] = localized_dt.astype('int64') / 10**9

    system_check_df = system_check_df.sort_values('check_time')
    check_df = pd.read_csv(f'{silver_url}/check_schedule.csv', parse_dates=['check_time', 'system_check_time'], date_format='%Y-%m-%d %H:%M:%S')

    # build finalized_training_df
    training_df = pd.DataFrame()
    try:
        training_df = pd.read_csv(f'{silver_url}/training_features.csv', parse_dates=['current_time', 'departure_time'])
        today = pd.Timestamp.now().normalize()
        training_df = training_df[training_df['current_time'].dt.normalize() == today]
    except Exception as e:
        print('no past training features')
    # if it is current time check!
    while len(system_check_df) > 0:
        curr_time = time.time()
        lower_bound = curr_time
        upper_bound = curr_time + 60

        current_time_mask = (system_check_df['check_time'] >= lower_bound) & (system_check_df['check_time'] <= upper_bound)
        _system_check_df = system_check_df[current_time_mask]
        print(_system_check_df)
        temp_training_df = load_arrival_status(oba_api_key=oba_api_key, bronze_url=bronze_url, system_check_df=_system_check_df[['system_check_time', 'stop_id']], check_df=check_df, rush_hour_intervals=[datetime.time(6, 30), datetime.time(9, 30), datetime.time(15, 0), datetime.time(18, 30)])
        if len(temp_training_df) > 0:
            print('adding', len(temp_training_df), 'new training features to the database')
            training_df = pd.concat([training_df, temp_training_df], ignore_index=True)

        system_check_df = system_check_df[~current_time_mask]
        
        print(curr_time, '----> len(df) ---->', len(temp_training_df))
        training_df.to_csv(f'{silver_url}/training_features.csv')
        time.sleep(60)