import sys, os
import random
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from locust import FastHttpUser, events, task, between, run_single_user
from owslib.wms import WebMapService

from utils.random_bbox import generate_random_bbox

import requests
import logging

logger = logging.getLogger(__name__)


class LayerNameArgError(Exception):
    def handle_error(self, environment):
        """
        Handle the error by logging and stopping the environment.
        """
        logger.error(str(self))
        environment.runner.quit()  # Gracefully stop the Locust runner if you need to terminate the entire test
        sys.exit(
            str(self)
        )  # Provide an error message directly to the console if running in a standalone mode


# extend command line to allow a random-seed (for random bbox creation) and
# argument for bbox area
@events.init_command_line_parser.add_listener
def init_parser(parser):
    parser.add_argument(
        "--random-seed",
        type=int,
        default=1640,
        help="Random seed used to generate the bbox, this is important to prevent server/client caching. Usefull to replicate random bbox. If no seed then 1640 value will be used",
    )
    parser.add_argument(
        "--layer-name",
        type=str,
        default="",
        help="Layer to be used for benchmarking. if not set, will default to service's first layer",
    )
    parser.add_argument(
        "--bbox-area",
        type=float,
        default=100.0,
        help="Bounding box area in square meters or square degrees, depending on projection used. Defaults is 100km2 or 10x10km on bbox-ratio=1.0",
    )
    parser.add_argument(
        "--bbox-ratio",
        type=float,
        default=1.0,
        help="Bounding box width/height ratio, better to keep it as 1.0 (square)",
    )
    

class WMSBenchmark(FastHttpUser):
    """
    A class to model the benchmarking of a WMS layer using Locust.
    """

    # TODO: extend code to allow seetting CRS's EPGS available

    # The base URL for the host
    # Without this predefined class atribute the __main__ code can't set the host. It seems like a bug on locust
    host = ""

    # Defines a wait time of 1 to 2 seconds between consecutive tasks executed by a simulated user
    wait_time = between(1, 2)

    def on_start(self):
        """
        On start, fetch the WMS capabilities to determine layers and other parameters.
        """
        # Timout extended for very slow servers
        self.client.timeout = 120  # timeout is in seconds

        self.wms = WebMapService(self.host)
        self.layers = self.get_layers()
        self.layer_name = self.environment.parsed_options.layer_name
        logger.info(f"layer_name is {'empty' if self.layer_name == '' else self.layer_name}")
        if self.layer_name:
            if self.layer_name not in self.layers:
                error_message = (
                    f"The specified WMS layer '{self.layer_name}' is not available WMS service'{self.wms.identification.title}'. "
                    f"Please check the layer name for any typos or omit the '--layer-name' argument to use the first available layer.  "
                    f"Available layers: {self.layers}"
                )
                raise LayerNameArgError(error_message)
            else:
                pass  # all good with layer name
        else:  # user didnt defined layer
            logger.info(
                f"No  --layer-name argument value, using first layer available in service"
            )
            self.layer_name = self.layers[0]  # we will only use the first layer

        self.layer = self.wms.contents[self.layer_name]

        # get layej proj
        # self.srs = "EPSG:3763"  #'EPSG:3763' layer.boundingBox[-1] # Assuming EPSG:3763 for demonstration. Extract from GetCapabilities for dynamic approach.
        self.crs = self.get_crs()
        # self.layer_mimetype = urllib.parse.quote(
        # For now the first format available later to do also as argument
        self.layer_mimetype = self.wms.getOperationByName("GetMap").formatOptions[0]  # ['image/jpeg']
        self.layer_mimetype = "image/png"
        self.bbox = (
            self.get_bbox()
        )  # A generic BBOX, ideally parse GetCapabilities for valid ranges.

        self.bbox_generator = generate_random_bbox(
            *self.get_bbox(),
            area=self.environment.parsed_options.bbox_area,
            ratio=self.environment.parsed_options.bbox_ratio,
            seed=self.environment.parsed_options.random_seed,
        )
        logger.info(f"bbox area in km2:{self.environment.parsed_options.bbox_area}")
        logger.info(f"bbox aspect ration:{self.environment.parsed_options.bbox_ratio}")
        logger.info(f"bbox random seed:{self.environment.parsed_options.random_seed}")

    def get_bbox(self):
        """
        Get the bbox from layer.boundinBox
        """
        return (
            self.layer.boundingBox[0],
            self.layer.boundingBox[1],
            self.layer.boundingBox[2],
            self.layer.boundingBox[3],
        )

    def get_crs(self):
        """
        Gets the src from owslib layer's bbox, the last element is the srs information as EPSG:3763
        """
        # TODO: check if we get a real EPSG code
        # ['EPSG:4258', 'EPSG:3857', 'EPSG:25831', 'EPSG:25832', 'EPSG:28992', 'EPSG:4326']
        epgs_code = self.layer.boundingBox[-1]
        return epgs_code

    def get_layers(self):
        """
        Fetch and parse the GetCapabilities document to retrieve layer names.
        """
        layers = list()
        for layer in self.wms.contents:
            layers.append(layer)
        return layers

    @task
    def load_map(self):
        """
        A task that loads a map image from the WMS layer using a random BBOX.
        """
        # For simplicity, selecting the first layer. Adjust as needed.
        # layer = self.layers[0] if self.layers else "no-layer-available"

        # Lets get a random bbx
        bbox = next(self.bbox_generator)
        # bbox = next(generate_random_bbox(*self.bbox))
        bbox_str = ",".join(map(str, bbox))

        url_path = self.get_url(bbox_str)
        
        # Making the GET request to load the map
        logger.debug(f"URL for request: {url_path}")
        response = self.client.get(url_path)
    
    def get_url(self,bbox_str):
        """
        Construct a URL for a GetMap request to the WMS service.

        This method constructs a URL using the base host URL and additional query parameters 
        required for the WMS GetMap request. The `urllib.parse` module is used to handle cases 
        where the base host URL already contains query parameters.

        Parameters:
        bbox_str (str): A string representing the bounding box coordinates in the format 
                        "minx,miny,maxx,maxy".

        Returns:
        str: The full URL for the WMS GetMap request.
        
        Example:
        bbox_str = "-143566.40427116063,36617.15748174256,-133566.40427116063,46617.15748174256"
        full_url = get_url(bbox_str)
        # Example return URL:
        # "https://ortos.dgterritorio.gov.pt/cgi-bin/mapserv.exe?map=%2Fms4w%2Fapps%2Fmapfile%2Fmosaico2023.map&service=WMS&version=1.3.0&request=GetMap&layers=ortoSat2023-CorVerdadeira&styles=&bbox=-143566.40427116063%2C36617.15748174256%2C-133566.40427116063%2C46617.15748174256&width=512&height=512&crs=EPSG%3A3763&format=image%2Fpng"
        """
        
        """
        From the bbox string numbers it creates a url based on class (self) information, 
        implements urllib.parse due to https://host/cgi-bin/mapserv.exe?map=/mapfiles/my.map
        url structure that implements ? on its url causing conflicts with url queries 
        
        bbox_str example -143566.40427116063,36617.15748174256,-133566.40427116063,46617.15748174256
        """
        # TODO: obtain WMS and version from generic class arguments
        # TODO: Width/Height is not implementend
        
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetMap",
            "layers": self.layer_name,
            "styles": "",
            "bbox": bbox_str,
            "width": "512",
            "height": "512",
            "crs": self.crs,
            "format": self.layer_mimetype
            }
        # Parse the base URL
        url_parts = urlparse(self.host)

        # Extract existing query parameters
        query_params = parse_qs(url_parts.query)

        # Update the query parameters with the new ones
        query_params.update(params)

        # Rebuild the query string
        new_query = urlencode(query_params, doseq=True)

        # Construct the new URL
        new_url_parts = url_parts._replace(query=new_query)
        full_url = urlunparse(new_url_parts)

        return full_url


# Example running code snippet would be similar to your WMTS benchmark
if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    from locust import run_single_user
    from locust.env import Environment

    # Initialize the environment
    env = Environment(user_classes=[WMSBenchmark])
    env.create_local_runner()

    wms_benchmark = WMSBenchmark(env)
    env.parsed_options = type("", (), {})()  # Create a simple class to hold options

    #wms_benchmark.host = "https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0"
    wms_benchmark.host="https://ortos.dgterritorio.gov.pt/cgi-bin/mapserv.exe?map=/ms4w/apps/mapfile/mosaico2023.map"
    env.parsed_options.random_seed = 72
    env.parsed_options.bbox_area = 100  # square km (10km x 10km)
    env.parsed_options.bbox_ratio = 1.0
    env.parsed_options.layer_name = "" # None default to pick up first layer
    wms_benchmark.environment = env
    # Directly call the on_start to use the setup (if any exception handling, do here)
    try:
        wms_benchmark.on_start()
    except Exception as e:
        print("An error occurred during setup:", str(e))
        exit()

    # Assuming we are just testing the setup, you might not need to run any tasks, but if you do:
    wms_benchmark.load_map()  # Directly run the task method
    env.runner.quit()
