#!/bin/bash

# This script helps set up a drive to be mounted at ~/video-data
# It must be run with root privileges

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

# Function to list available drives
list_drives() {
    echo "Available drives:"
    echo "----------------"
    lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,UUID | grep "disk\|part"
    echo
}

# Function to get UUID of a partition
get_uuid() {
    local device=$1
    blkid -s UUID -o value $device
}

# Function to check if drive is already mounted
is_mounted() {
    local device=$1
    mountpoint -q "$device"
    return $?
}

# Create mount point if it doesn't exist
MOUNT_POINT="/home/${SUDO_USER}/video-data"
mkdir -p "$MOUNT_POINT"
chown ${SUDO_USER}:${SUDO_USER} "$MOUNT_POINT"

# List available drives
list_drives

# Get drive selection from user
read -p "Enter the device to mount (e.g., /dev/sdb1): " DEVICE

# Validate device exists
if [ ! -b "$DEVICE" ]; then
    echo "Error: $DEVICE is not a valid block device"
    exit 1
fi

# Get UUID of the device
UUID=$(get_uuid $DEVICE)
if [ -z "$UUID" ]; then
    echo "Error: Could not get UUID for $DEVICE"
    exit 1
fi

# Check filesystem type
FS_TYPE=$(blkid -s TYPE -o value $DEVICE)
if [ -z "$FS_TYPE" ]; then
    echo "Error: Could not determine filesystem type for $DEVICE"
    exit 1
fi

# Create fstab entry
FSTAB_ENTRY="UUID=$UUID $MOUNT_POINT $FS_TYPE defaults 0 2"

# Backup fstab
cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d_%H%M%S)

# Check if entry already exists
if grep -q "$MOUNT_POINT" /etc/fstab; then
    echo "Warning: Entry for $MOUNT_POINT already exists in fstab"
    read -p "Do you want to replace it? (y/n): " REPLACE
    if [ "$REPLACE" = "y" ]; then
        sed -i "\|$MOUNT_POINT|d" /etc/fstab
    else
        echo "Aborting..."
        exit 1
    fi
fi

# Add entry to fstab
echo "$FSTAB_ENTRY" >> /etc/fstab

# Test mount
echo "Testing mount..."
mount -a

if [ $? -eq 0 ]; then
    echo "Success! Drive has been mounted at $MOUNT_POINT"
    echo "Testing write permissions..."
    su - ${SUDO_USER} -c "touch $MOUNT_POINT/test_write"
    if [ $? -eq 0 ]; then
        echo "Write test successful"
        su - ${SUDO_USER} -c "rm $MOUNT_POINT/test_write"
    else
        echo "Warning: Write test failed. Check permissions."
    fi
else
    echo "Error: Mount failed. Check /etc/fstab entry"
    # Restore backup
    cp /etc/fstab.backup.$(date +%Y%m%d_%H%M%S) /etc/fstab
    exit 1
fi

# Update config.local.ini if it exists
CONFIG_FILE="/home/${SUDO_USER}/video-data/config.local.ini"
if [ -f "$CONFIG_FILE" ]; then
    echo "Updating config.local.ini with new paths..."
    sed -i "s|directory = .*|directory = $MOUNT_POINT|" "$CONFIG_FILE"
    sed -i "s|backup_directory = .*|backup_directory = ${MOUNT_POINT}_backup|" "$CONFIG_FILE"
    chown ${SUDO_USER}:${SUDO_USER} "$CONFIG_FILE"
fi

echo "
Setup complete! The drive will automatically mount at $MOUNT_POINT on boot.
Current mount status:"
df -h "$MOUNT_POINT"
