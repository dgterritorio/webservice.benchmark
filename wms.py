import itertools
import logging
import math
import os
import random
import sys
from base64 import b64encode
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from gevent.lock import Semaphore
from locust import FastHttpUser, events, task, between, constant_throughput
from owslib.util import Authentication
from owslib.wms import WebMapService

logger = logging.getLogger(__name__)

_USER_IDS = itertools.count()  # distinct, reproducible random stream per simulated user
_CAPABILITIES = {}  # GetCapabilities parsed once per process, not once per user
_CAPABILITIES_LOCK = Semaphore()  # users starting together wait for the first fetch instead of repeating it
_POINTS = {}  # --points file -> list of (x, y), read once per process


def load_points(path):
    """(x, y) bbox centres from a CSV with an x,y header, e.g. mainland_points.csv (EPSG:3763)."""
    if path not in _POINTS:
        with open(path) as f:
            next(f)
            _POINTS[path] = [tuple(float(v) for v in line.split(",")) for line in f if line.strip()]
    return _POINTS[path]


class LayerNameArgError(Exception):
    def handle_error(self, environment):
        """
        Handle the error by logging and stopping the environment.
        """
        logger.error(str(self))
        environment.runner.quit()  # Gracefully stop the Locust runner if you need to terminate the entire test
        sys.exit(str(self))  # Provide an error message directly to the console if running in a standalone mode


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
    # Added 2026-11: authentication, layer mix, zoom mix, request rate and response validation.
    parser.add_argument(
        "--layers",
        type=str,
        default="",
        help="Weighted layer mix, e.g. 'layerA:55,layerB:15'. Overrides --layer-name.",
    )
    parser.add_argument(
        "--bbox-areas",
        type=str,
        default="",
        help="Comma-separated bbox areas in km2, one picked at random per request (zoom mix), e.g. '1,10,100'. "
        "Overrides --bbox-area.",
    )
    parser.add_argument(
        "--crs",
        type=str,
        default="",
        help="CRS for GetMap, e.g. EPSG:3857 (must be advertised for the layer). "
        "Default: the layer's first BoundingBox CRS.",
    )
    parser.add_argument(
        "--points",
        type=str,
        default="",
        help="CSV of x,y bbox centres (e.g. mainland_points.csv, mainland Portugal in EPSG:3763; needs --crs "
        "EPSG:3763). Without it the bbox is drawn anywhere in the layer extent, sea and Spain included.",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="image/png",
        help="GetMap format (default image/png). image/jpeg sends far fewer bytes on orthophotos.",
    )
    parser.add_argument("--width", type=int, default=512, help="GetMap width in pixels (default 512)")
    parser.add_argument("--height", type=int, default=512, help="GetMap height in pixels (default 512)")
    parser.add_argument(
        "--user-rps",
        type=float,
        default=0.0,
        help="Requests per second per user (constant throughput), so total rate = users x this value. "
        "Default 0 keeps the 1-2 s wait between requests.",
    )
    parser.add_argument(
        "--caps-ratio",
        type=float,
        default=0.0,
        help="Fraction of requests that are GetCapabilities instead of GetMap, e.g. 0.001 (default 0).",
    )
    parser.add_argument(
        "--wms-user",
        type=str,
        default=os.getenv("WMS_USER", ""),
        help="HTTP Basic Auth user (default: env WMS_USER)",
    )
    parser.add_argument(
        "--wms-password",
        type=str,
        default=os.getenv("WMS_PASSWORD", ""),
        is_secret=True,
        help="HTTP Basic Auth password (default: env WMS_PASSWORD; prefer the env var, the command line is visible in ps)",
    )


@events.init.add_listener
def on_init(environment, **kwargs):
    """Apply --user-rps before any user starts (wait_time is a class attribute)."""
    opts = environment.parsed_options
    if opts is not None and getattr(opts, "user_rps", 0) > 0:
        WMSBenchmark.wait_time = constant_throughput(opts.user_rps)


def mercator(lon, lat):
    """WGS84 lon/lat to EPSG:3857 metres."""
    return lon * 20037508.342789244 / 180, math.log(math.tan((90 + lat) * math.pi / 360)) * 6378137.0


def random_bbox(rng, minx, miny, maxx, maxy, area_km2, ratio):
    """A random bbox of area_km2 (map units in metres) inside the full extent; same rule as utils.random_bbox."""
    height = math.sqrt(area_km2 / ratio) * 1000
    width = ratio * height
    x = rng.uniform(minx, max(minx, maxx - width))
    y = rng.uniform(miny, max(miny, maxy - height))
    return (x, y, x + width, y + height)


class WMSBenchmark(FastHttpUser):
    """
    A class to model the benchmarking of a WMS layer using Locust.
    """

    # The base URL for the host
    # Without this predefined class atribute the __main__ code can't set the host. It seems like a bug on locust
    host = ""

    # Defines a wait time of 1 to 2 seconds between consecutive tasks executed by a simulated user
    # (replaced by constant_throughput when --user-rps is set)
    wait_time = between(1, 2)

    # Timeouts extended for very slow servers (seconds)
    network_timeout = 120.0
    connection_timeout = 120.0

    def on_start(self):
        """
        On start, fetch the WMS capabilities (once per process) to determine layers and other parameters.
        """
        opts = self.environment.parsed_options
        self.headers = {}
        if opts.wms_user:
            token = b64encode(f"{opts.wms_user}:{opts.wms_password}".encode()).decode()
            self.headers["Authorization"] = f"Basic {token}"

        self.wms = self.get_wms(opts)
        self.layers = list(self.wms.contents)

        # Layer mix: --layers 'a:55,b:15', else the single --layer-name, else the first layer
        if opts.layers:
            pairs = [item.rsplit(":", 1) for item in opts.layers.split(",") if item.strip()]
            mix = [(name.strip(), float(weight)) for name, weight in pairs]
        else:
            if not opts.layer_name:
                logger.info("No --layer-name argument value, using first layer available in service")
            mix = [(opts.layer_name or self.layers[0], 1.0)]
        for name, _ in mix:
            if name not in self.layers:
                raise LayerNameArgError(
                    f"The specified WMS layer '{name}' is not available in WMS service "
                    f"'{self.wms.identification.title}'. Available layers: {self.layers}"
                )
        self.layer_names = [name for name, _ in mix]
        self.layer_weights = [weight for _, weight in mix]
        self.layer_name = self.layer_names[0]  # kept for backwards compatibility
        self.extents = {name: self.get_extent(name, opts.crs) for name in self.layer_names}

        self.areas = [float(a) for a in opts.bbox_areas.split(",")] if opts.bbox_areas else [opts.bbox_area]
        if opts.points and opts.crs != "EPSG:3763":
            raise LayerNameArgError(f"--points holds EPSG:3763 coordinates, so it needs --crs EPSG:3763 (got '{opts.crs}')")
        self.points = load_points(opts.points) if opts.points else None
        self.layer_mimetype = opts.format
        user_id = next(_USER_IDS)
        # The worker index keeps users of different --processes apart (each process counts users from 0).
        worker = getattr(self.environment.runner, "worker_index", 0)
        self.rng = random.Random(f"{opts.random_seed}-{worker}-{user_id}")
        if user_id == 0:
            logger.info(f"layers (weight): {list(zip(self.layer_names, self.layer_weights))}")
            logger.info(f"bbox areas in km2: {self.areas}, aspect ratio: {opts.bbox_ratio}, seed: {opts.random_seed}")
            logger.info(f"extents: {self.extents}")

    def get_wms(self, opts):
        key = (self.host, opts.wms_user)
        with _CAPABILITIES_LOCK:
            if key not in _CAPABILITIES:
                auth = Authentication(opts.wms_user, opts.wms_password) if opts.wms_user else None
                _CAPABILITIES[key] = WebMapService(self.host, version="1.3.0", auth=auth, timeout=120)
        return _CAPABILITIES[key]

    def get_extent(self, layer_name, crs):
        """
        (minx, miny, maxx, maxy, crs) of a layer: its first BoundingBox, or the one for --crs.
        """
        layer = self.wms.contents[layer_name]
        if not crs:
            return tuple(layer.boundingBox[:5])
        for box in getattr(layer, "crs_list", None) or []:
            if box[4] == crs:
                return tuple(box[:5])
        wgs84 = getattr(layer, "boundingBoxWGS84", None)
        if crs == "EPSG:3857" and wgs84:  # servers often advertise only the native CRS box; derive Web Mercator
            west, south, east, north = wgs84[:4]
            return (*mercator(west, south), *mercator(east, north), crs)
        raise LayerNameArgError(
            f"Layer '{layer_name}' has no BoundingBox in {crs}; available: {[b[4] for b in layer.crs_list]}"
        )

    def get_bbox(self):
        """
        Get the bbox of the first layer (kept for backwards compatibility)
        """
        return self.extents[self.layer_name][:4]

    def get_crs(self):
        """
        Gets the CRS of the first layer's extent (kept for backwards compatibility)
        """
        return self.extents[self.layer_name][4]

    def get_layers(self):
        """
        Fetch and parse the GetCapabilities document to retrieve layer names.
        """
        return list(self.wms.contents)

    @task
    def load_map(self):
        """
        A GetMap of a random bbox on a layer from the mix, or (with --caps-ratio) a GetCapabilities.
        Responses that are not an image count as failures (MapServer can answer 200 with an XML exception).
        """
        opts = self.environment.parsed_options
        if opts.caps_ratio and self.rng.random() < opts.caps_ratio:
            url = self.service_url({"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"})
            with self.client.get(url, name="GetCapabilities", headers=self.headers, catch_response=True) as resp:
                if resp.status_code != 200 or "WMS_Capabilities" not in (resp.text or ""):
                    resp.failure(f"HTTP {resp.status_code}, not a capabilities document")
            return

        layer = self.rng.choices(self.layer_names, weights=self.layer_weights)[0]
        minx, miny, maxx, maxy, crs = self.extents[layer]
        area = self.rng.choice(self.areas)
        if self.points:
            cx, cy = self.rng.choice(self.points)
            height = math.sqrt(area / opts.bbox_ratio) * 1000
            width = opts.bbox_ratio * height
            bbox = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
        else:
            # Same random calls, in the same order, as before --points existed: seed 1640 repeats old runs.
            bbox = random_bbox(self.rng, minx, miny, maxx, maxy, area, opts.bbox_ratio)
        url_path = self.get_url(",".join(map(str, bbox)), layer=layer, crs=crs)
        logger.debug(f"URL for request: {url_path}")
        with self.client.get(url_path, name=f"GetMap {layer}", headers=self.headers, catch_response=True) as resp:
            ctype = resp.headers.get("Content-Type", "") if resp.headers else ""
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
            elif not ctype.startswith("image/"):
                resp.failure(f"not an image ({ctype}): {(resp.text or '')[:120]}")

    def service_url(self, params):
        """
        The host URL with params merged into its query string (the host may already carry ?map=...).
        """
        url_parts = urlparse(self.host)
        query_params = parse_qs(url_parts.query)
        query_params.update(params)
        return urlunparse(url_parts._replace(query=urlencode(query_params, doseq=True)))

    def get_url(self, bbox_str, layer=None, crs=None):
        """
        Construct a URL for a GetMap request to the WMS service.

        This method constructs a URL using the base host URL and additional query parameters
        required for the WMS GetMap request. The `urllib.parse` module is used to handle cases
        where the base host URL already contains query parameters.

        Parameters:
        bbox_str (str): A string representing the bounding box coordinates in the format
                        "minx,miny,maxx,maxy".
        layer (str): layer name (default: the first layer of the mix)
        crs (str): CRS of bbox_str (default: that layer's extent CRS)

        Returns:
        str: The full URL for the WMS GetMap request.

        Example:
        bbox_str = "-143566.40427116063,36617.15748174256,-133566.40427116063,46617.15748174256"
        full_url = get_url(bbox_str)
        # Example return URL:
        # "https://ortos.dgterritorio.gov.pt/cgi-bin/mapserv.exe?map=%2Fms4w%2Fapps%2Fmapfile%2Fmosaico2023.map&service=WMS&version=1.3.0&request=GetMap&layers=ortoSat2023-CorVerdadeira&styles=&bbox=-143566.40427116063%2C36617.15748174256%2C-133566.40427116063%2C46617.15748174256&width=512&height=512&crs=EPSG%3A3763&format=image%2Fpng"
        """
        layer = layer or self.layer_name
        opts = self.environment.parsed_options
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetMap",
            "layers": layer,
            "styles": "",
            "bbox": bbox_str,
            "width": str(getattr(opts, "width", 512)),
            "height": str(getattr(opts, "height", 512)),
            "crs": crs or self.extents[layer][4],
            "format": self.layer_mimetype,
        }
        return self.service_url(params)


# Example running code snippet would be similar to your WMTS benchmark
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
    from locust.env import Environment

    # Initialize the environment
    env = Environment(user_classes=[WMSBenchmark])
    env.create_local_runner()

    wms_benchmark = WMSBenchmark(env)
    env.parsed_options = type("", (), {})()  # Create a simple class to hold options

    # wms_benchmark.host = "https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0"
    wms_benchmark.host = "https://ortos.dgterritorio.gov.pt/cgi-bin/mapserv.exe?map=/ms4w/apps/mapfile/mosaico2023.map"
    env.parsed_options.random_seed = 72
    env.parsed_options.bbox_area = 100  # square km (10km x 10km)
    env.parsed_options.bbox_ratio = 1.0
    env.parsed_options.layer_name = ""  # None default to pick up first layer
    env.parsed_options.layers = ""
    env.parsed_options.bbox_areas = ""
    env.parsed_options.crs = ""
    env.parsed_options.width = env.parsed_options.height = 512
    env.parsed_options.caps_ratio = 0.0
    env.parsed_options.wms_user = env.parsed_options.wms_password = ""
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
