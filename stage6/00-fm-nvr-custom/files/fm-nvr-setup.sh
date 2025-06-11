#!/bin/bash
set -e

LOG_TAG="fm-nvr-firstboot"
echo "[$LOG_TAG] Starting FrontiersMarket NVR first boot setup script..."

VIDEO_SCRIPTS_DIR="/opt/python-video-scripts"
# This is the main setup script *within* your python-video-scripts repository
MAIN_APP_SETUP_SCRIPT="${VIDEO_SCRIPTS_DIR}/setup.sh"
MARKER_FILE="/opt/fm-nvr-setup-complete" # Marker to prevent re-running

if [ -f "${MARKER_FILE}" ]; then
    echo "[$LOG_TAG] First boot setup already completed (marker file found: ${MARKER_FILE}). Exiting."
    exit 0
fi

echo "[$LOG_TAG] Marker file not found. Proceeding with setup."

# Wait a bit for network and Tailscale to be fully up, if necessary
# sleep 10 # Optional: uncomment if setup.sh relies on immediate network/Tailscale connectivity

if [ -x "${MAIN_APP_SETUP_SCRIPT}" ]; then
    echo "[$LOG_TAG] Executing main application setup script: ${MAIN_APP_SETUP_SCRIPT}"
    cd "${VIDEO_SCRIPTS_DIR}"
    # Execute your application's setup script
    # Pass any necessary environment variables or arguments if required
    if ./setup.sh; then
        echo "[$LOG_TAG] Main application setup script completed successfully."
    else
        echo "[$LOG_TAG][ERROR] Main application setup script failed. See logs for details."
        # Decide if you want to exit without creating the marker file if setup fails
        exit 1
    fi
else
    echo "[$LOG_TAG][WARNING] Main application setup script not found or not executable: ${MAIN_APP_SETUP_SCRIPT}"
    # If this script is optional, you might not want to exit with an error.
    # If it's mandatory, then `exit 1` might be appropriate here.
fi

echo "[$LOG_TAG] Creating marker file to indicate completion: ${MARKER_FILE}"
date > "${MARKER_FILE}"
sync # Ensure marker file is written to disk

echo "[$LOG_TAG] FrontiersMarket NVR first boot setup finished successfully."
exit 0
