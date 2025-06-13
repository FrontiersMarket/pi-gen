#!/bin/bash
set -e

# This script runs inside the pi-gen build environment for stage6

VIDEO_SCRIPTS_SOURCE_DIR="./files/python-video-scripts"  # Path relative to 01-run.sh execution
VIDEO_SCRIPTS_TARGET_DIR_IN_IMAGE="/opt/fm-nvr/python-video-scripts"

echo "[STAGE6 CUSTOM SCRIPT] Preparing to copy python-video-scripts into image..."
echo "Source in build env: ${VIDEO_SCRIPTS_SOURCE_DIR}"
echo "Target in image: ${VIDEO_SCRIPTS_TARGET_DIR_IN_IMAGE}"

mkdir -p "${ROOTFS_DIR}${VIDEO_SCRIPTS_TARGET_DIR_IN_IMAGE}"

echo "[STAGE6 CUSTOM SCRIPT] Copying python-video-scripts..."
cp -r "${VIDEO_SCRIPTS_SOURCE_DIR}/." "${ROOTFS_DIR}${VIDEO_SCRIPTS_TARGET_DIR_IN_IMAGE}/"
echo "[STAGE6 CUSTOM SCRIPT] python-video-scripts copied to ${ROOTFS_DIR}${VIDEO_SCRIPTS_TARGET_DIR_IN_IMAGE}"

INSTALL_SH_PATH_IN_IMAGE="${VIDEO_SCRIPTS_TARGET_DIR_IN_IMAGE}/install.sh"
if [ -f "${ROOTFS_DIR}${INSTALL_SH_PATH_IN_IMAGE}" ]; then
    echo "[STAGE6 CUSTOM SCRIPT] Making install.sh executable: ${INSTALL_SH_PATH_IN_IMAGE}"
    chmod +x "${ROOTFS_DIR}${INSTALL_SH_PATH_IN_IMAGE}"

    echo "[STAGE6 CUSTOM SCRIPT] Running install.sh in chroot environment..."
    on_chroot << EOF_CHROOT
cd "${VIDEO_SCRIPTS_TARGET_DIR_IN_IMAGE}"
if ./install.sh; then
    echo "[STAGE6 CUSTOM SCRIPT][CHROOT] install.sh executed successfully."
else
    echo "[STAGE6 CUSTOM SCRIPT][CHROOT][ERROR] install.sh execution failed."
fi
EOF_CHROOT
else
    echo "[STAGE6 CUSTOM SCRIPT][WARNING] install.sh not found at ${ROOTFS_DIR}${INSTALL_SH_PATH_IN_IMAGE}. Skipping execution."
fi

echo "[STAGE6 CUSTOM SCRIPT] Customizations complete."
