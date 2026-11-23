"""Generate a fixed list of points inside mainland Portugal (EPSG:3763), for land-only benchmark requests.

    python3 make_mainland_points.py nuts1.json mainland_points.csv

nuts1.json is the WFS GetFeature of caop_continente:cont_nuts1 (one MultiPolygon, the mainland) in GeoJSON with
srsName=EPSG:3763. Points are uniform over the land area (rejection sampling), seed 1640, so the file is
reproducible. The scripts pick bbox centres from this file with --points.
"""
import json
import random
import sys

import shapely

N = 20000
SEED = 1640

geom = shapely.geometry.shape(json.load(open(sys.argv[1]))["features"][0]["geometry"])
shapely.prepare(geom)
minx, miny, maxx, maxy = geom.bounds
rng = random.Random(SEED)
points = []
while len(points) < N:
    x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
    if shapely.contains_xy(geom, x, y):
        points.append((round(x), round(y)))
with open(sys.argv[2], "w") as f:
    f.write("x,y\n")
    f.writelines(f"{x},{y}\n" for x, y in points)
print(f"{len(points)} points, area {geom.area / 1e6:.0f} km2, bounds {[round(v) for v in geom.bounds]}")
