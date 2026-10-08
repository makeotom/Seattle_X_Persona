'''
Makeo Tom
8-5-26
load schedule and buildtraining data into csv files overtime
responsible for creating a schedule to load all csv data and save the resuts as training data
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

load_dotenv()

def groupby_n_time_diff(sub_df: DataFrame, n):
    '''
    return:
    ['start_time', 'end_time', 'route_ids', 'departure_count']

    args:
    sub_df: index: scheduled_departure_time -> ['route_id', 'ride_id']
    n: minutes after
    '''
    n = pd.Timedelta(minutes=n)

    sub_df = sub_df.sort_index()
    sub_df['scheduled_departure_time'] = sub_df.index
    exceding_delta = (sub_df['scheduled_departure_time'] - sub_df['scheduled_departure_time'].shift()) > n # time till next arrival > n min
    group_ids = exceding_delta.cumsum()
    groups = sub_df.groupby(group_ids).agg(start_time=('scheduled_departure_time', 'min'), end_time=('scheduled_departure_time', 'max'), route_ids=('route_id', set), departure_count=('route_id', 'count'))
    return groups

def optimize_check_schedule(df: DataFrame, min_before, min_after, interval, system_check_interval=20):
    '''
    given df orderded by its departures, optimize requests by having returning check schedule
    return:
    ['stop_id', 'route_ids', 'check_time']

    args:
    df: index: scheduled_departures -> ['stop_id', 'route_id', 'ride_id', 'stop_seq']
    '''
    # (1) group by time intervals
    df = df.groupby('stop_id').apply(groupby_n_time_diff, n=max(min_before + interval, min_after + interval))
    df = df.reset_index(drop=False)
    df = df[['stop_id', 'start_time', 'end_time', 'route_ids', 'departure_count']]

    # (2) expand the time interval to a individual check time
    interval = pd.Timedelta(minutes=interval)
    min_before = pd.Timedelta(minutes=min_before)
    min_after = pd.Timedelta(minutes=min_after)
    df['start_time'] = df['start_time'] - min_before
    df['end_time'] = df['end_time'] + min_after
    df['check_time'] = df.apply(lambda row: pd.date_range(start=row['start_time'], end=row['end_time'], freq=interval), axis=1)
    df = df.explode('check_time', ignore_index=True)

    # (3) assign system check time for each stops for check times (every 20 minutes)
    df = df[['stop_id', 'route_ids', 'check_time', 'departure_count']]
    # ----> group by stop id, then group into 20 min intervl, then get the min time for the window transformation!
    # df['check'] = df['check_time']
    df['system_check_time'] = df.groupby(['stop_id', pd.Grouper(key='check_time', freq='20min')])['check_time'].transform('max')
    # df = df.rename(columns={'check':'check_time'})
    return df

def return_check_schedule(oba_api_key, bronze_url, check_num_before=3, check_num_after=3, check_interval=5):
    '''
    return dataframe which has all times for bus arrival status to be checked as follows:
    return:
    stop_id, route_id, scheduled_departure_time, ride_id, system_ check_order, system_check_order

    args:
    check_num_before = 3 # represents the amount of checks to be done before scheduled arrival
    check_num_after = 3 # represents the amount of checks to be done after scheduled arrival
    check_interval = 5 # represents interval between checks for arrival status
    '''
    client = OnebusawaySDK(api_key=oba_api_key)
    df = pd.read_csv(f'{bronze_url}/timestamp.csv', parse_dates=True)

    # (1) get current date time and set it as the index
    # check_time, stop_id, route_id, ride_id, arrival_time, departure_time, stop_seq, la_time
    todays_date = int(client.current_time.retrieve().current_time / 1000)
    todays_date = pd.Timestamp(str(pd.Timestamp(todays_date, unit='s', tz='America/Los_Angeles').date()))

    df['departure_time'] = pd.to_datetime(df['departure_time'], unit='s', utc=True)
    deltas = df['departure_time'] - df['departure_time'].dt.normalize()
    df['check_time'] = todays_date.normalize() + deltas
    df = df.set_index('check_time')

    # (2) select only important columns, optimize timestamps dataframe
    # check_time, stop_id, route_id, ride_id, 
    df = df[['stop_id', 'route_id', 'ride_id', 'stop_seq']]
    df = optimize_check_schedule(df, min_before=check_num_before * check_interval, min_after=check_num_after * check_interval, interval=check_interval)

    return df


def load_check_schedule(silver_url: str, bronze_url: str, oba_api_key: str):
    check_schedule = return_check_schedule(oba_api_key, bronze_url=bronze_url)
    print(check_schedule)
    check_schedule.to_csv(f'{silver_url}/check_schedule.csv', index=False)

    # TODO return a link to a temporary file that stores all of the unieue system check times and build this directly into the scheduler
    system_check_schedule = check_schedule.groupby(['stop_id', 'system_check_time'])['check_time'].count()
    system_check_schedule = system_check_schedule.reset_index()[['stop_id', 'system_check_time']]

    url = f'{silver_url}/system_check_schedule.csv'
    system_check_schedule.to_csv(url, index=False)

    return url