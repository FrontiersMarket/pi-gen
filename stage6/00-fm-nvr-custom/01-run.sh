#!/bin/bash
set -e

# TAILSCALE_AUTHKEY is expected to be in the environment, passed from pi-gen/config
if [ -z "$TAILSCALE_AUTHKEY" ]; then
  echo "ERROR: TAILSCALE_AUTHKEY environment variable is not set. Cannot install Tailscale."
  exit 1
fi

echo "Starting custom NVR setup (01-run.sh)..."

# Install Tailscale
echo "Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sh
echo "Tailscale installation script finished."

# Enable Tailscale service to start on boot
systemctl enable --now tailscaled
echo "Tailscale service enabled."

# Authenticate Tailscale
# Using --accept-routes to allow access to subnet routers or exit nodes if configured in Tailscale ACLs.
# Using --ssh to enable Tailscale SSH for accessing the Pi.
# Add any other tags or options as needed, e.g., --advertise-tags=tag:nvr
echo "Authenticating Tailscale with auth key..."
tailscale up --authkey "${TAILSCALE_AUTHKEY}" --accept-routes --ssh
echo "Tailscale 'up' command executed."

# Copy python-video-scripts from the 'files' directory (placed there by build.sh)
# to its final destination in the image.
APP_SOURCE_DIR="${STAGE_DIR}/00-fm-nvr-custom/files/python-video-scripts"
APP_DEST_DIR="/opt/python-video-scripts"

echo "Copying python-video-scripts from ${APP_SOURCE_DIR} to ${APP_DEST_DIR}..."
mkdir -p "${APP_DEST_DIR}"
cp -r "${APP_SOURCE_DIR}/." "${APP_DEST_DIR}/" # Note the . to copy contents
echo "python-video-scripts copied."

# Copy and enable the first-boot setup service and script
FIRSTBOOT_SERVICE_FILE="fm-nvr-firstboot.service"
FIRSTBOOT_SCRIPT_FILE="fm-nvr-setup.sh"
FILES_DIR="${STAGE_DIR}/00-fm-nvr-custom/files"

echo "Setting up first-boot service..."
# Copy service file to systemd directory
cp "${FILES_DIR}/${FIRSTBOOT_SERVICE_FILE}" "/etc/systemd/system/${FIRSTBOOT_SERVICE_FILE}"
# Copy the setup script (it's already in /opt/python-video-scripts if it's part of that repo,
# otherwise copy it to a known location like /usr/local/sbin)
# For this example, fm-nvr-setup.sh is a separate script we provide.
cp "${FILES_DIR}/${FIRSTBOOT_SCRIPT_FILE}" "${APP_DEST_DIR}/${FIRSTBOOT_SCRIPT_FILE}" # Place it alongside other scripts
chmod +x "${APP_DEST_DIR}/${FIRSTBOOT_SCRIPT_FILE}"

# Enable the first-boot service
systemctl enable "${FIRSTBOOT_SERVICE_FILE}"
echo "First-boot service (${FIRSTBOOT_SERVICE_FILE}) enabled."

# Ensure scripts are executable (if python-video-scripts has its own setup.sh)
if [ -f "${APP_DEST_DIR}/setup.sh" ]; then
    chmod +x "${APP_DEST_DIR}/setup.sh"
    echo "${APP_DEST_DIR}/setup.sh made executable."
fi

# Clean APT cache
apt-get clean

echo "Custom NVR setup (01-run.sh) completed."
