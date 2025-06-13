#!/bin/bash

# This script sets up and starts the RTSP streamer service via systemd.
# It must be run with root privileges.

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR/.."
WORKDIR=$(pwd)

# Get stream name from argument
STREAM_NAME="$1"
if [ -z "$STREAM_NAME" ]; then
    echo "Error: Stream name must be provided"
    echo "Usage: $0 <stream_name>"
    echo "Example: $0 front"
    exit 1
fi

PYTHON_EXEC="python3"

echo "Creating systemd service for RTSP streamer ($STREAM_NAME)..."
SERVICE_NAME="rtsp_streamer_${STREAM_NAME}"
cat <<EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=RTSP Streamer Service (${STREAM_NAME})
After=network.target

[Service]
Type=simple
WorkingDirectory=${WORKDIR}
User=fm
Environment=PYTHONUNBUFFERED=1
ExecStart=${PYTHON_EXEC} ${WORKDIR}/rtsp_streamer.py --stream_name ${STREAM_NAME}
StandardOutput=append:/var/log/rtsp_streamer_${STREAM_NAME}.log
StandardError=append:/var/log/rtsp_streamer_${STREAM_NAME}.error.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling and starting RTSP streamer service ($STREAM_NAME)..."
systemctl enable ${SERVICE_NAME}.service
systemctl start ${SERVICE_NAME}.service

echo "RTSP streamer service started successfully."
