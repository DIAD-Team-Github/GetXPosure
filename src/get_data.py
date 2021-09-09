import os
from pathlib import Path
from datetime import datetime as pydt
import errno
import glob

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import gpxpy

feature_server_url = r'https://services1.arcgis.com/E5n4f1VY84i0xSjy/arcgis/rest/services/Exposure_Sites_for_WEB/FeatureServer'
root = Path(os.path.dirname(__file__)).parent
data = os.path.join(root,'data') #Used for caching exposure location CSVs
if not os.path.exists(data):
    os.mkdir(data)    
tformat = "%Y%m%dT%H%M%S" #CSV filename time format   

def parse_time(text):
    """Function used to parse the various time formats in use by ACT Health

    Args:
        text (str): string time

    Returns:
        str: standardised time format string HH:MM:SS
    """
    formats = ['%I:%M %p','%I:%M:%S %p','%H:%M:%S']
    out_format = '%H:%M:%S'
    for fmt in formats:
        try:
            dt = pydt.strptime(text, fmt)
            return pydt.strftime(dt,out_format)
        except ValueError:
            pass
    try:
        dt = pydt.strptime(text, '%H:%M %p') 
        return pydt.strftime(dt,out_format)
    except ValueError:
        pass
    return None

def parse_gpx(gpx_path):
    """Function for parsing a single gpx file into a GeoDataFrame

    Args:
        gpx_path (str): Path to gpx file

    Returns:
        GeoDataFrame: gdf containing all the points in the gpx
    """

    gpx_file = open(gpx_path, 'r')

    gpx = gpxpy.parse(gpx_file)

    points = []

    for track in gpx.tracks:
        for segment in track.segments:
            points.extend([(pt.time,pt.latitude,pt.longitude,pt.elevation) for pt in segment.points])

    points.extend([(wp.time,wp.latitude,wp.longitude,wp.elevation) for wp in gpx.waypoints])

    for route in gpx.routes:
        points.extend([(pt.time,pt.latitude,pt.longitude,pt.elevation) for pt in route.points])
        
    df = pd.DataFrame(points, columns=['time', 'latitude', 'longitude','elevation'])
    df['time_epoch'] = df['time'].apply(lambda x: x.timestamp())

    gdf = gpd.GeoDataFrame(df,geometry=gpd.points_from_xy(df.longitude, df.latitude))
    gdf.crs = 4326

    return gdf


    
def get_gpx_locations(gpx_dir):
    """"Parse each of the .gpx files in the directory and return a single geodataframe"""

    if not os.path.exists(gpx_dir):
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), f"{gpx_dir}")

    gpx_paths = glob.glob(os.path.join(gpx_dir, "*.gpx")) 
    
    if len(gpx_paths) < 1: 
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), f"No gpx files found in {gpx_dir}")
        
    
    print(f" - {len(gpx_paths)} gpx file(s) found")

    gpx_gdf = gpd.GeoDataFrame()

    for gpx_path in gpx_paths:

        gdf = parse_gpx(gpx_path)
        
        gdf = gdf.to_crs(7855) # Project to MGA2020 Zone 55

        gpx_gdf = gpx_gdf.append(gdf)

    gpx_gdf = gpx_gdf.reset_index()
    gpx_gdf['time'] = gpx_gdf['time'].dt.tz_convert('Australia/Canberra')

    return gpx_gdf

def get_exposure_locations(csv_path=None,max_age_hours=6):
    """Function for getting the ACT covid exposure locations as a geopandas GeoDataFrame

    Args:
        csv_path (str, optional): Path to write the csv out to if a new one is required (age of most up-to-date one is greater than max_age_hours). Defaults to None.
        max_age_hours (int, optional): The maximum age in hours of the most recent covid exposure locations csv. Defaults to 6. Age is taken from csv names in data folder.

    Returns:
        [type]: [description]
    """
    # Get all the CSVs in the data folder with filenames matching tformat
    csv_files = glob.glob(os.path.join(data, "*.csv")) 
    for f in csv_files:
        try:
            pydt.strptime(os.path.basename(f),tformat+".csv")
        except ValueError:
            csv_files.remove(f)

    if len(csv_files)>0:
        newest_csv = sorted(csv_files)[-1]
        file_time = pydt.strptime(os.path.basename(newest_csv).split('.')[0],tformat)
        diff = pydt.now()-file_time
        
        #If there is one more recent than max_age_hours read it into a geodataframe and return
        if (diff.seconds/3600) < max_age_hours:
            print(" - Recent data found in folders")
            
            df = pd.read_csv(newest_csv, parse_dates=['arrival_dt','departure_dt','USER_Date'])
            
            df = df.dropna(subset=['geometry'])
            
            df['geometry'] = gpd.GeoSeries.from_wkt(df['geometry'])
            
            gdf = gpd.GeoDataFrame(df,geometry="geometry")

            gdf.crs = 7855
            
            return gdf

    #Otherwise get an updated dataset from ACT health
    print(" - Getting new exposure locations data from ACT Health")
    from arcgis.features import FeatureLayerCollection

    sites = FeatureLayerCollection(feature_server_url)
    sites_layer = sites.layers[0]

    results = sites_layer.query(where='X>0') #query for all points
    
    df = results.sdf
    df = df.rename(columns={"SHAPE": "geometry"})
    gdf = gpd.GeoDataFrame(df)
    
    # Some points have missing shapes, so populate from lat and long values
    def fill_geom(row):
        row.geometry = Point(row.X,row.Y)
        return row
    gdf[gdf['geometry'].isna()] = gdf[gdf['geometry'].isna()].apply(fill_geom,axis=1)
    
    gdf.crs=4326 #Set as WGS84
    gdf = gdf.to_crs(7855) #Project to MGA2020 Zone 55

    # Construct arrival and departure datetimes from the date and time columns
    gdf['USER_ArrivalTime'] = gdf['USER_ArrivalTime'].apply(parse_time)
    gdf['arrival_dt'] = gdf['USER_Date'].astype(str) +' '+ gdf['USER_ArrivalTime']
    gdf['arrival_dt'] = gdf['arrival_dt'].astype('datetime64[ns]')

    gdf['USER_DepartureTime'] = gdf['USER_DepartureTime'].apply(parse_time)
    gdf['departure_dt'] = gdf['USER_Date'].astype(str) +' '+ gdf['USER_DepartureTime']
    gdf['departure_dt'] = gdf['departure_dt'].astype('datetime64[ns]')

    gdf['departure_dt'] = gdf['departure_dt'].dt.tz_localize('Australia/Canberra').dt.tz_convert('Australia/Canberra')
    gdf['arrival_dt'] = gdf['arrival_dt'].dt.tz_localize('Australia/Canberra').dt.tz_convert('Australia/Canberra')
    gdf['USER_Date'] = gdf['USER_Date'].dt.tz_localize('Australia/Canberra').dt.tz_convert('Australia/Canberra')

    # Add arrival and departure times to common epoch to simplify later calculations
    gdf['arrival_epoch'] = gdf['arrival_dt'].apply(lambda x: x.timestamp())
    gdf['departure_epoch'] = gdf['departure_dt'].apply(lambda x: x.timestamp())

    # Cache as csv
    if csv_path is None: 
        csv_path = os.path.join(data,pydt.strftime(pydt.now(),tformat+".csv"))
    gdf.to_csv(csv_path, index=False)

    return gdf