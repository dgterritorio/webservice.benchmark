FROM docker.io/python:3.12.3-slim-bookworm@sha256:2be8daddbb82756f7d1f2c7ece706aadcb284bf6ab6d769ea695cc3ed6016743
# docker build --no-cache --progress=plain -t website.benchmark:v0.0.1 -f Dockerfile .
# docker run --rm benchmark:v0.0.1 -f wms.py --help

COPY wms.py wmts.py /
COPY utils /utils
COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

# Define an entrypoint to allow passing arguments to the scripts
ENTRYPOINT ["locust"]

