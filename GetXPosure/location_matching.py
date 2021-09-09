import numpy as np
from datetime import datetime as pydt

def EDM(A,B):
    """Calculates a Eucliddean Distanc Matrix from two numpy arrays with x,y/easting,northing values (for fast proximity analysis)"""

    p1 = np.sum(A**2, axis=1)[:,np.newaxis]
    p2 = np.sum(B**2, axis=1)
    p3 = -2 * np.dot(A,B.T)

    return np.round(np.sqrt(p1+p2+p3),2)

def show_matches(gpx_gdf,exp_gdf,minimum_distance=100):
    """Function for finding matches between exposure locations and gpx points

    Args:
        gpx_gdf (GeoDataFrame): GPX locations
        exp_gdf (GeoDataFrame): Exposure locations
        minimum_distance (int, optional): the minimum distance in meters for an exposure and gpx point to be a match. Defaults to 100m.
    """
    # Get the euclidean distance matrices
    A = np.vstack(gpx_gdf['geometry'])
    B = np.vstack(exp_gdf['geometry'])
    distances = EDM(A,B)

    # Get the arrival/departure time and presence time difference matrices
    arrivals = np.array(exp_gdf['arrival_epoch'])
    departures = np.array(exp_gdf['departure_epoch'])
    presence = np.array(gpx_gdf['time_epoch'])
    pre_array = arrivals[None, :] - presence[:, None] #arrival - my time, so I was there after their arrival if it's negative
    post_array = departures[None, :] - presence[:, None] #departure - my time, so I was there before their departure if it's positive

    # Create a stacked array of distances and time differences
    exposure_array = np.stack((distances,pre_array,post_array))
    
    # Query for any points in the array where the distance is considered a match and the time differences indicate a match to exposure times
    results = np.where((exposure_array[0,:,:]<minimum_distance) & (exposure_array[1,:,:]<0) & (exposure_array[2,:,:]>0))

    # Turn the query into indices for the geodataframes
    index_pairs = [(results[0][n],results[1][n]) for n in range(len(results[0]))]

    # Report each matched pair of exposure location and first matching gpx point
    if len(index_pairs) > 0: 
        print("\nEXPOSURE(S) FOUND! ------")
    
        while len(index_pairs) > 0:

            gpx_id, exp_id = index_pairs[0]
            
            index_pairs = [pair for pair in index_pairs if exp_id != pair[1]] #Remove all other instances of matches on this exposure site

            # Get the points using index
            my_point = gpx_gdf.iloc[gpx_id]
            exposure_location = exp_gdf.iloc[exp_id]
            
            # Format datetimes and display
            exp_date = pydt.strftime(exposure_location.USER_Date,'%d/%m/%Y')
            exp_arr = pydt.strftime(exposure_location.arrival_dt,'%H:%M %p')
            exp_dept = pydt.strftime(exposure_location.departure_dt,'%H:%M %p')
            my_time = pydt.strftime(my_point.time, '%H:%M %p')

            print(f"You were within {minimum_distance}m of {exposure_location.USER_SiteName} at the time it was a '{exposure_location.USER_Contact}' exposure site on {exp_date}")
            print(f"First of your matching point(s): {round(my_point.latitude,4)},{round(my_point.longitude,4)} at {my_time}")
            print(f"Exposure point: {round(exposure_location.Y,4)},{round(exposure_location.X,4)} from {exp_arr} to {exp_dept}\n")
    else:
        print("All good - no potential exposures found")