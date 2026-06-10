import xarray as xr
import matplotlib.pyplot as plt
import earthaccess

def generate_png(input_nc_path, output_img_path):
    ds = xr.open_dataset(input_nc_path)
   
    u_current = ds['u'].isel(time=0)
    
    plt.figure(figsize=(10, 6))
    u_current.plot(x='longitude', y='latitude', cmap='viridis')
    plt.title("OSCAR Ocean Currents (u)")
    
    plt.savefig(output_img_path, bbox_inches='tight')
    plt.close() 

earthaccess.login()
results = earthaccess.search_data(
    short_name="OSCAR_L4_OC_NRT_V2.0",
    temporal="2026-06-04",
    count=1
)

downloaded_files = earthaccess.download(results, local_path=".")

local_filepath = downloaded_files[0]

generate_png(local_filepath, "map.png")
