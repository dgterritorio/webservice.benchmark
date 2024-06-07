#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Check if the correct number of arguments is provided
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <host_url> <layer_name>"
    exit 1
fi

# Assign arguments to variables
HOST_URL=$1
LAYER_NAME=$2

# Navigate to the benchmark directory
cd /opt/webservice.benchmark

# Generate a random seed with 4 digits
RANDOM_SEED=$(shuf -i 1000-9999 -n 1)

# Replace special characters in host URL for the filename
HOST_SANITIZED=$(echo "$HOST_URL" | sed 's|https://||; s|/|_|g')

# Define the Docker command with the new random seed
docker run --rm -v $(pwd)/reports:/reports -v $(pwd)/logs:/logs \
website.benchmark:v0.0.1 \
-f wmts.py  --host "$HOST_URL" \
--random-seed $RANDOM_SEED  --layer-name "$LAYER_NAME" \
--headless -u 100 -r 10 -t 4m \
--html /reports/${HOST_SANITIZED}_${LAYER_NAME}_u100_r10_t4_s${RANDOM_SEED}.html \
--loglevel DEBUG --logfile /logs/${HOST_SANITIZED}_${LAYER_NAME}_u100_r10_t4_s${RANDOM_SEED}.log
