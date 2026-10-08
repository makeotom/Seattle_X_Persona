'''
load all oba static data into csv files
including the following:
    routes
    stops
    stop time schedules
'''

# oba api
import os
from dotenv import load_dotenv
from onebusaway import OnebusawaySDK

# quick optimization
from sortedcontainers import SortedDict

# main dataframe operations and validations
import pandas as pd
from pandas import DataFrame
import pandera.pandas as pa
from transformations.load_static_schema import RouteSchema, TripSchema, StopSchema, StopRouteSchema, TimestampSchema

# timestamp/datetime handeling
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# geo data handeling
import polyline
import geopandas as gpd
from geopandas import GeoDataFrame
import shapely
from shapely import Point, LineString
from pyproj import Transformer

def add_route(route_id, _route_df, _trip_df, _stop_df, _stop_route_df, _timestamp_df, client):
    '''
    add a route to the dataframes
    '''

    # (0) create individual dataframes
    route_df = DataFrame(
        {
            'route_id': [],
            'route_name': []
        }
    )
    trip_df = DataFrame(
        {
            'route_id': [],
            'trip_id': [],
            'trip_headsign': [],
            'average_distance_between_stops': []
        }
    )
    stop_df = DataFrame(
        {
            'stop_id': [],
            'stop_name': [],
            'stop_direction': [],
            'lon': [],
            'lat': []
        }
    )
    stop_route_df = DataFrame(
        {
            'stop_id': [],
            'route_id': [],
            'trip_id': [],
            'stop_seq': []
        }
    )
    timestamp_df = DataFrame(
        {
            'stop_id': [],
            'route_id': [],
            'trip_id': [],
            'ride_id': [],
            'arrival_time': [],
            'departure_time': [],
            'stop_seq': []
        }
    )


    # (1) actual retrieve all information about route
    res = client.schedule_for_route.retrieve(route_id=route_id).to_dict()
    stop_res_df = pd.json_normalize(res['data']['references']['stops'])

    if res['code'] == 200:
        # (a) add route
        row_df = DataFrame([{'route_id': route_id, 'route_name': res['data']['references']['routes'][0]['shortName']}])
        route_df = pd.concat([route_df, row_df], ignore_index=True)

        # (b) add the all trips for the route
        trips = res['data']['entry']['stopTripGroupings']
        for trip_id, trip in enumerate(trips):
            # add trip for many trips
            trip_headsign = '\\n'.join(trip['tripHeadsigns'])
            row_df = DataFrame([{'route_id': route_id, 'trip_id': trip_id, 'trip_headsign': trip_headsign}])
            trip_df = pd.concat([trip_df, row_df], ignore_index=True)
        
            # (c) add stops (for each trip add its stops)
            stop_ids_df = DataFrame({'stop_id': trip['stopIds']})
            stop_ids_df = stop_ids_df[~(stop_ids_df['stop_id'].isin(list(stop_df['stop_id'])))]
            row_stop_df = pd.merge(left=stop_ids_df, right=stop_res_df[['id', 'name', 'lon', 'lat', 'direction']], how='left', left_on='stop_id', right_on='id')
            row_stop_df = row_stop_df.rename(columns={'stop_id': 'stop_id', 'name': 'stop_name', 'direction': 'stop_direction', 'lon': 'lon', 'lat': 'lat'}).drop(columns='id')
            row_stop_df = row_stop_df.reset_index(level=0, drop=True)
            stop_df = pd.concat([stop_df, row_stop_df], ignore_index=True)

            # (d) and stop_routes
            row_stop_route_df = row_stop_df[['stop_id']]
            row_stop_route_df['route_id'] = route_id
            row_stop_route_df['trip_id'] = trip_id
            row_stop_route_df['stop_seq'] = row_stop_route_df.index
            stop_route_df = pd.concat([stop_route_df, row_stop_route_df], ignore_index=True)

            # (e) add all timestamps of arrival and departure
            rides = trip['tripsWithStopTimes']
            for ride in rides:
                stop_time_df = ride['stopTimes']
                stop_time_df = DataFrame(stop_time_df)
                stop_time_df = stop_time_df[['arrivalTime', 'departureTime', 'stopId', 'tripId']]
                stop_time_df = stop_time_df.rename(columns={'arrivalTime': 'arrival_time', 'departureTime': 'departure_time', 'stopId': 'stop_id', 'tripId': 'ride_id'})
                stop_time_df['trip_id'] = trip_id
                stop_time_df['route_id'] = route_id
                stop_time_df['stop_seq'] = stop_time_df.reset_index(level=0, drop=True).index
                # TODO remove once testing is done
                timestamp_df = pd.concat([timestamp_df, stop_time_df], ignore_index=True)
    else:
        raise ConnectionRefusedError('OBA API - schedule_for_route could not be called')

    # (1a) verify all data frames integrity
    verify_schemas(route_df, trip_df, stop_df, stop_route_df, timestamp_df)

    # (2) get the average distance per trip for all trips
    res = client.stops_for_route.list(route_id=route_id)
    if res.code == 200:
        # (a) decode a poly line for each trip (trip_id)
        path_for_trips = {} # {trip_id -> [point(lat, lon)]}
        if len(res.data.entry.stop_groupings) >= 1:
            trips = res.data.entry.stop_groupings[0].to_dict()['stopGroups']
            for trip_id, trip in enumerate(trips):
                points = []
                for i, pline in enumerate(trip['polylines']):
                    points.extend(polyline.decode(pline['points'], precision=5))
                path_for_trips[trip_id] = points

        # (b) get distances between all stops for each trip (trip_id)
        average_distances = []
        for trip_id in path_for_trips.keys():
            # (1) get a list of line segements representing path by:
                # convert all points to meters -> (project to utm washington)
            coords = path_for_trips[trip_id]
            transformer = Transformer.from_crs('EPSG:4326', 'EPSG:32618', always_xy=True)
            grouped_coords = [[Point(transformer.transform(xx=coords[i][1], yy=coords[i][0])), Point(transformer.transform(xx=coords[i + 1][1], yy=coords[i + 1][0]))] for i in range(len(coords) - 1)]
            path_segements = [LineString(pair) for pair in grouped_coords]

            # (2) retrieve all stops in the current trip and
                # longitude lattitude of the current stop
                # longitude lattitude of the next stop in sequence
            stop_path_df = stop_route_df
            stop_path_df = stop_path_df[(stop_path_df['route_id'] == route_id) & (stop_path_df['trip_id'] == trip_id)]
            # 1 order by stop seq
            stop_path_df = stop_path_df.sort_values(by='stop_seq')
            # 2 join longitude lattudede from stop_df
            stop_path_df = pd.merge(stop_path_df, stop_df[['stop_id', 'lon', 'lat', 'stop_name']], on='stop_id', how='left')
            # 3 have new 2 columns of longitude and lattitude of the next stop (drop last row)
            #   stop_path_df['n.stop_id', 'n.lon', 'n.lat']
            stop_path_df['n.stop_id'] = stop_path_df['stop_id'].shift(-1)
            stop_path_df['n.lon'] = stop_path_df['lon'].shift(-1)
            stop_path_df['n.lat'] = stop_path_df['lat'].shift(-1)
            stop_path_df = stop_path_df[:-1]

            # (3) retrieve all the distances of current stop to next stop (per trip)
            def calculate_distance(row):
                '''
                given row with lon, lat, n.lon, n.lat, calculate the distances
                '''
                lon = float(row['lon'])
                lat = float(row['lat'])
                point_a = Point(transformer.transform(xx=lon, yy=lat))
                lonb = float(row['n.lon'])
                latb = float(row['n.lat'])
                point_b = Point(transformer.transform(xx=lonb, yy=latb))
                # if the stops location isnt in the path
                # instead of one check do a check for each path
                segements_a = []
                segements_b = []
                for i, segment in enumerate(path_segements):
                    if segment.buffer(20).contains(point_a):
                        segements_a.append(i)
                    if segment.buffer(20).contains(point_b):
                        segements_b.append(i)

                # calculate distance between a and b
                # TODO the if statements below might have false logic - temporary fix
                # TODO real solution is to add data validation (build a schema to check if the other routes have wierd problems)
                start = 0
                if len(segements_a) > 0:
                    start = segements_a[len(segements_a) - 1]
                end = len(path_segements) - 1
                if len(segements_b) > 0:
                    end = segements_b[len(segements_b) - 1]

                distance = 0
                cursor = point_a
                for i in range(start + 1, end + 1):
                    current = grouped_coords[i][0]
                    distance += cursor.distance(current)
                    cursor = current
                distance += cursor.distance(point_b)
                row['distance'] = distance
                return row
                
            stop_path_df = stop_path_df.apply(calculate_distance, axis=1)
            avg = stop_path_df['distance'].mean()
            # average_distances[trip_id] = avg
            average_distances.append(avg)

        # save avg distance between stops for all paths in route
        trip_df.loc[trip_df['route_id'] == route_id, 'average_distance_between_stops'] = average_distances
    else:
        raise ConnectionRefusedError('OBA API - stops_for_route could not be called')

    # (2a) data validation
    verify_schemas(route_df, trip_df, stop_df, stop_route_df, timestamp_df)

    # (3) concat the dataframes
    route_df = pd.concat([route_df, _route_df], ignore_index=True)
    trip_df = pd.concat([trip_df, _trip_df], ignore_index=True)
    stop_df = pd.concat([stop_df, _stop_df], ignore_index=True)
    stop_route_df = pd.concat([stop_route_df, _stop_route_df], ignore_index=True)
    timestamp_df = pd.concat([timestamp_df, _timestamp_df], ignore_index=True)

    return [route_df, trip_df, stop_df, stop_route_df, timestamp_df]

def verify_schemas(route_df, trip_df, stop_df, stop_route_df, timestamp_df):
    try:
        RouteSchema.validate(route_df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        print(exc)
    try:
        TripSchema.validate(trip_df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        print(exc)
    try:
        StopSchema.validate(stop_df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        print(exc)
    try:
        StopRouteSchema.validate(stop_route_df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        print(exc)
    try:
        TimestampSchema.validate(timestamp_df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        print(exc)

def get_uw_routes(client: OnebusawaySDK):
    '''
    returns all bus routes going in udistrict area
    '''

    lattitude = 47.659254957498064
    longitude = -122.31320597215536
    radius=2500 # m
    res = client.stops_for_location.list(lat=lattitude, lon=longitude, radius=radius)
    if res.code == 200:
        res = res.data.references.routes
        return [(elem.id) for elem in res]

    print('error retrieving uw routes')
    return []

def main(routes=None, api_key=None, bronze_url=None):
    '''
    run everything
    '''
    route_df = DataFrame(
        {
            'route_name': []
        }
    )
    trip_df = DataFrame(
        {
            'route_id': [],
            'trip_id': [],
            'trip_headsign': [],
            'average_distance_between_stops': []
        }
    )

    stop_df = DataFrame(
        {
            'stop_id': [],
            'stop_name': [],
            'stop_direction': [],
            'lon': [],
            'lat': []
        }
    )

    stop_route_df = DataFrame(
        {
            'stop_id': [],
            'route_id': [],
            'trip_id': [],
            'stop_seq': []
        }
    )

    timestamp_df = DataFrame(
        {
            'stop_id': [],
            'route_id': [],
            'trip_id': [],
            'ride_id': [],
            'arrival_time': [],
            'departure_time': [],
            'stop_seq': []
        }
    )

    saved = [route_df, trip_df, stop_df, stop_route_df, timestamp_df]

    # start functionality
    # route_ids = ['40_100479', '1_100169']
    client = OnebusawaySDK(api_key=api_key)
    route_ids = []
    if routes:
        route_ids = routes
    else:
        route_ids = get_uw_routes(client)

    for route_id in route_ids:
        dfs = add_route(route_id=route_id, _route_df=saved[0], _trip_df=saved[1], _stop_df=saved[2], _stop_route_df=saved[3], _timestamp_df=saved[4], client=client)
        saved = dfs

    # save to file
    names = ['route', 'trip', 'stop', 'stop_route', 'timestamp']
    for i, df in enumerate(saved):
        print(df.head())
        df.to_csv(f'{bronze_url}/{names[i]}.csv', index=False)

def extract_transform_load_raw(routes: list, api_key: str, bronze_url: str) -> bool:
    main(routes=routes, api_key=api_key, bronze_url=bronze_url)
    return True