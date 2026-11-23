"""WFS load: GetFeature (GeoJSON) on random bboxes, to load the GeoServer pods and watch their HPA.

    locust -f wfs.py,step_shape.py --host https://geo.dgterritorio.gov.pt/wfs/caop_continente \
        --type-name caop_continente:cont_freguesias --steps 10,20,40,60 --step-time 420 \
        --stop-fail-pct 20 --stop-p95-ms 30000 --headless --html reports/wfs.html

Each user sends one request at a time with no pause, so users = requests in flight (the GeoServer
control-flow limits concurrency, not rate). Requests whose bbox fell on sea or Spain are reported
as "GetFeature (empty)"; if ALL are empty, the bbox or the type name is wrong.

Checked 2026-11-18 over Lisbon: bbox in EPSG:3763 with the ",EPSG:3763" suffix is x,y order.
Avoid cos-s2:cos2023_features here: one "Rede rodoviaria" polygon is 9.5 MB of GeoJSON and nearly
every bbox touches it, so that test measures bandwidth, not the WFS.
"""

import itertools
import math
import random

from locust import FastHttpUser, constant, events, task

_USER_IDS = itertools.count()
_POINTS = {}  # --points file -> list of (x, y), read once per process


def load_points(path):
    """(x, y) bbox centres from a CSV with an x,y header, e.g. mainland_points.csv (EPSG:3763)."""
    if path not in _POINTS:
        with open(path) as f:
            next(f)
            _POINTS[path] = [tuple(float(v) for v in line.split(",")) for line in f if line.strip()]
    return _POINTS[path]


@events.init_command_line_parser.add_listener
def _wfs_args(parser):
    parser.add_argument("--type-name", type=str, default="caop_continente:cont_freguesias", help="WFS typeNames")
    parser.add_argument("--bbox-areas", type=str, default="16,64,256", help="Comma-separated bbox areas in km2, one picked per request")
    parser.add_argument("--count", type=int, default=100, help="Maximum features per request (default 100)")
    parser.add_argument(
        "--extent",
        type=str,
        default="-119000,-300000,163000,277000",
        help="Where bboxes are drawn, minx,miny,maxx,maxy in EPSG:3763 (default: mainland Portugal)",
    )
    parser.add_argument("--random-seed", type=int, default=1640, help="Seed for the bboxes (default 1640)")
    parser.add_argument(
        "--points",
        type=str,
        default="",
        help="CSV of x,y bbox centres in EPSG:3763 (e.g. mainland_points.csv); replaces --extent, so bboxes stay on land",
    )


class WFSBenchmark(FastHttpUser):
    host = ""
    wait_time = constant(0)
    network_timeout = 120.0
    connection_timeout = 120.0

    def on_start(self):
        opts = self.environment.parsed_options
        self.extent = [float(v) for v in opts.extent.split(",")]
        self.areas = [float(a) for a in opts.bbox_areas.split(",")]
        # The worker index keeps users of different --processes apart (each process counts users from 0).
        worker = getattr(self.environment.runner, "worker_index", 0)
        self.rng = random.Random(f"{opts.random_seed}-{worker}-{next(_USER_IDS)}")
        self.points = load_points(opts.points) if opts.points else None

    @task
    def get_feature(self):
        opts = self.environment.parsed_options
        minx, miny, maxx, maxy = self.extent
        side = math.sqrt(self.rng.choice(self.areas)) * 1000
        if self.points:
            cx, cy = self.rng.choice(self.points)
            x, y = cx - side / 2, cy - side / 2
        else:
            x = self.rng.uniform(minx, maxx - side)
            y = self.rng.uniform(miny, maxy - side)
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": opts.type_name,
            "count": str(opts.count),
            "outputFormat": "application/json",
            "srsName": "EPSG:3763",
            "bbox": f"{x:.0f},{y:.0f},{x + side:.0f},{y + side:.0f},EPSG:3763",
        }
        # Real clients (QGIS, browsers) ask for compression, so Traefik's gzip CPU is part of the test.
        with self.client.get(
            "", params=params, headers={"Accept-Encoding": "gzip"}, name="GetFeature", catch_response=True
        ) as resp:
            head = resp.content[:200] if resp.content else b""
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
            elif not head.startswith(b'{"type":"FeatureCollection"'):
                resp.failure(f"not GeoJSON: {head[:120]!r}")
            elif b'"features":[]' in head:
                resp.request_meta["name"] = "GetFeature (empty)"
                resp.success()
            else:
                resp.success()
