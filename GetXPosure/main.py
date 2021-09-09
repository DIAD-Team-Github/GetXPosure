from get_data import get_exposure_locations, get_gpx_locations
from location_matching import show_matches

gpx_dir = r"<PATH TO YOUR DIRECTORTY CONTAINING GPX FILES>"

# Get the exposure points ---
exp_gdf = get_exposure_locations()

# Collect all gpx points ---
gpx_gdf = get_gpx_locations(gpx_dir)

# Check for matches ---
show_matches(gpx_gdf,exp_gdf) #show_matches' minimum_distance key-word argument defaults to 100m

