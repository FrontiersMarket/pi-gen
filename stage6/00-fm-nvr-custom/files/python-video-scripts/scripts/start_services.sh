#!/bin/bash

# This script starts the uploader and all configured RTSP streamers

SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR"
cd .. # Move to project root

# Function to get list of stream configurations
get_stream_sections() {
    python3 -c '
import configparser
config = configparser.ConfigParser()
config.read("config.local.ini")
for section in config.sections():
    if section.startswith("Streamer."):
        print(section.split(".")[1])
'
}

# Start the uploader first
echo "Starting uploader service..."
bash "$SCRIPT_DIR/start_uploader.sh"

# Start a streamer for each configuration
echo "Starting RTSP streamer services..."
for stream in $(get_stream_sections); do
    echo "Starting streamer for $stream..."
    bash "$SCRIPT_DIR/start_rtsp_streamer.sh" "$stream"
done

exit 0
