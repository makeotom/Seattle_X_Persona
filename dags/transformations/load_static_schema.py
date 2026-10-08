import pandera.pandas as pa
import pandas as pd

class RouteSchema(pa.DataFrameModel):
    route_id: str = pa.Field(str_matches=r"^\d+_[A-Za-z0-9-_]+$", )
    route_name: str = pa.Field(str_matches="^[^\n]+$")

class TripSchema(pa.DataFrameModel):
    route_id: str = pa.Field(str_matches=r"^\d+_[A-Za-z0-9-_]+$")
    trip_id: int = pa.Field(ge=0)
    trip_headsign: str = pa.Field(str_matches=r"^[^\n]+$")
    average_distance_between_stops: float = pa.Field(ge=100, le=10_000, ignore_na=True, raise_warning=True)

class StopSchema(pa.DataFrameModel):
    stop_id: str = pa.Field(str_matches=r"^\d+_[A-Za-z0-9-_]+$")
    stop_name: str = pa.Field(str_matches=r"^[^\n]+$")
    stop_direction: str = pa.Field(str_matches=r"^[NESWnesw][NESWnesw]?$")
    lon: float = pa.Field(lt=360, gt=-360)
    lat: float = pa.Field(lt=360, gt=-360)

class StopRouteSchema(pa.DataFrameModel):
    stop_id: str = pa.Field(str_matches=r"^\d+_[A-Za-z0-9-_]+$")
    route_id: str = pa.Field(str_matches=r"^\d+_[A-Za-z0-9-_]+$")
    trip_id: int = pa.Field(ge=0)
    stop_seq: int = pa.Field(ge=0)

class TimestampSchema(pa.DataFrameModel):
    stop_id: str = pa.Field(str_matches=r"^\d+_[A-Za-z0-9-_]+$")
    route_id: str = pa.Field(str_matches=r"^\d+_[A-Za-z0-9-_]+$")
    trip_id: int = pa.Field(ge=0)
    ride_id: str = pa.Field(str_matches=r"^[^\n]+$")
    stop_seq: int = pa.Field(ge=0)
    arrival_time: int = pa.Field(ge=1_000, le=99_999)
    departure_time: int = pa.Field(ge=1_000, le=99_999)

if __name__ == '__main__':
    df = pd.DataFrame({
        'route_id': ['40_thishsodd', 'broken'],
        'trip_id': [1, 1.0],
        'trip_headsign': ['fdsfdfsd', 'hello\nsignma\ndfs'],
        'average_distance_between_stops': [1_000.0, 10.0]
    })

    try:
        TripSchema.validate(df, lazy=True)
        print('yo i passed')
    except pa.errors.SchemaErrors as e:
        print(e)
