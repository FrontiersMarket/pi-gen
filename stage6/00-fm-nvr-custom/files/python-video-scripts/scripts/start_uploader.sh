#!/bin/bash

# This script sets up and starts the uploader service via systemd.
# It must be run with root privileges.

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

SCRIPT_DIR="$(dirname "$0")"
cd "$SCRIPT_DIR/.."
WORKDIR="$(pwd)"

# Use virtual environment if it exists
if [ -d "${WORKDIR}/venv" ]; then
    PYTHON_EXEC="${WORKDIR}/venv/bin/python3"
else
    PYTHON_EXEC="python3"
fi

echo "Creating systemd service for uploader..."
cat <<EOF > /etc/systemd/system/uploader.service
[Unit]
Description=File Uploader Service
After=network.target

[Service]
Type=simple
WorkingDirectory=${WORKDIR}
User=fm
Group=fm
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=${WORKDIR}
ExecStart=/bin/bash -c '${PYTHON_EXEC} ${WORKDIR}/uploader.py 2>&1 | tee -a /var/log/uploader.log'
Restart=on-failure
RestartSec=5
TimeoutStartSec=0
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling and starting uploader service..."
systemctl enable uploader.service
systemctl start uploader.service

echo "Uploader service started successfully."
