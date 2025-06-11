# RTSP Video Stream Uploader

This system captures RTSP video streams, segments them into manageable chunks while preserving the original format, and automatically uploads them to Google Cloud Storage. The system is designed to be resilient to network interruptions and can automatically recover from camera disconnections or system restarts.

## Setup

1. Clone this repository

2. Set up storage drive (optional but recommended):
   ```bash
   sudo ./scripts/setup_video_drive.sh
   ```
   This script will:
   - List available drives
   - Help you select and mount a drive at `~/video-data`
   - Set up automatic mounting via `/etc/fstab`
   - Configure proper permissions
   - Update config paths automatically

3. Create your configuration:
   ```bash
   cp config.example.ini config.local.ini
   ```

4. Set up the Python environment:
   ```bash
   ./scripts/setup_env.sh
   ```
   This creates a virtual environment and installs all required dependencies.

## Configuration

### Local Configuration (config.local.ini)

Copy `config.example.ini` to `config.local.ini` and configure the following sections:

#### Uploader Section
```ini
[Uploader]
directory = ./test-data              # Directory to monitor for files
backup_directory = /path/to/backup   # Fallback directory if primary is full
min_free_space_gb = 10              # Switch to backup when space below this (GB)
bucket = your-bucket-name            # GCP bucket name (without gs:// prefix)
file_age_threshold = 60              # Wait time after file modification (seconds)
sleep_interval = 10                  # Scan interval (seconds)
credentials_file = /path/to/creds    # Path to GCP service account JSON
```

#### Streamer Sections
You can configure multiple streams using the format `[Streamer.NAME]` where NAME is a unique identifier:

```ini
[Streamer.front]
file_prefix = front_cam                    # Prefix for output files
rtsp_url = rtsp://user:pass@ip:port/path  # RTSP stream URL
output_dir = ./test-data                  # Where to save video segments
segment_time = 600                        # Segment duration (seconds)
sleep_interval = 5                        # Restart delay if stream fails

[Streamer.back]
file_prefix = back_cam
rtsp_url = rtsp://user:pass@ip:port/path
output_dir = ./test-data
segment_time = 600
sleep_interval = 5
```

Each stream configuration must have a unique `file_prefix` to distinguish its files.

### Google Cloud Setup

1. Create a service account in Google Cloud Console
2. Grant it the following roles:
   - Storage Object Creator
   - Storage Object Viewer
3. Download the service account key JSON file
4. Update the `credentials_file` path in your `config.local.ini`

## Storage Management

### Primary and Backup Storage
The system automatically manages storage space:
- Monitors available disk space in the primary directory
- Switches to backup directory if space falls below threshold (default: 10GB)
- Automatically returns to primary directory when space is available
- Creates backup directory if it doesn't exist

### Drive Setup
Use `setup_video_drive.sh` to:
- Mount a dedicated drive for video storage
- Configure automatic mounting on boot
- Set proper permissions
- Update configuration paths

Example:
```bash
$ sudo ./scripts/setup_video_drive.sh
Available drives:
----------------
NAME   SIZE TYPE MOUNTPOINT UUID
sda    500G disk
└─sda1 500G part

Enter the device to mount (e.g., /dev/sda1): /dev/sda1
```

## Scripts

All scripts are located in the `scripts/` directory:

### setup_video_drive.sh
Configures a dedicated drive for video storage:
```bash
sudo ./scripts/setup_video_drive.sh
```

### setup_env.sh
Sets up the Python virtual environment and installs dependencies.
```bash
./scripts/setup_env.sh
```

### start_rtsp_streamer.sh
Configures and starts an RTSP streamer as a systemd service. Requires the stream name as an argument.
```bash
sudo ./scripts/start_rtsp_streamer.sh front  # Start front camera stream
sudo ./scripts/start_rtsp_streamer.sh back   # Start back camera stream
```

### start_uploader.sh
Configures and starts the file uploader as a systemd service.
```bash
sudo ./scripts/start_uploader.sh
```

### start_services.sh
Starts the uploader service and all configured RTSP streamer services.
```bash
sudo ./scripts/start_services.sh
```
This will:
1. Start the uploader service
2. Read all `[Streamer.*]` sections from config
3. Start a separate service for each stream

## System Services

The scripts create multiple systemd services:

1. `rtsp_streamer_NAME.service`: One service per configured stream (e.g., rtsp_streamer_front.service)
2. `uploader.service`: Handles file uploads to Google Cloud Storage

Check service status:
```bash
systemctl status rtsp_streamer_front  # Check front camera stream
systemctl status rtsp_streamer_back   # Check back camera stream
systemctl status uploader            # Check uploader service
```

View logs:
```bash
journalctl -u rtsp_streamer_front  # View front camera logs
journalctl -u rtsp_streamer_back   # View back camera logs
journalctl -u uploader            # View uploader logs
```

## Video Management

### File Format and Segmentation
The RTSP stream is saved in segments while maintaining the original format:
- No re-encoding is performed
- Segments are aligned with wall clock time
- Filename format: `prefix_YYYYMMDD_HHMMSS.ts`
- Transport Stream (`.ts`) format preserves exact timing

### Video Stitching
Use the stitching script to combine video segments into a single file:

```bash
./scripts/stitch_videos.sh -i ./test-data -o output.mp4 -p front_cam -s 2025-02-01 -e 2025-02-03
```

Options:
- `-i, --input-dir DIR`: Directory containing video segments
- `-o, --output FILE`: Output video file
- `-p, --prefix NAME`: Stream prefix to filter (e.g., front_cam)
- `-s, --start-date DATE`: Start date (YYYY-MM-DD)
- `-e, --end-date DATE`: End date (YYYY-MM-DD)
- `-v, --verbose`: Enable verbose output

The script will:
1. Find all segments matching the criteria
2. Sort them chronologically
3. Stitch them together without re-encoding
4. Optimize the output for web playback

## Directory Structure
```
.
├── README.md
├── config.example.ini          # Example configuration template
├── config.local.ini           # Your local configuration (git-ignored)
├── requirements.txt           # Python dependencies
├── rtsp_streamer.py          # RTSP stream capture script
├── scripts/                  # Service management scripts
│   ├── setup_env.sh
│   ├── start_rtsp_streamer.sh
│   ├── start_services.sh
│   └── start_uploader.sh
├── test-data/               # Video segments directory (git-ignored)
└── uploader.py             # GCP upload script
```

## Docker

- The docker/ directory contains a containerized version of stitch_video.py and includes two new flags, --gcs-bucket to set the GCS Cloud Storage bucket to read/write from, --batchsize which allows an option to set the max number of files to process
- There is Cloud SDK code within the script but commented out until further testing, currently using gcsfuse mount option to attach to GCS

## Security Notes

- The `config.local.ini` and service account JSON files are git-ignored for security
- Never commit credentials or configuration with sensitive data
- Keep your service account key secure and restrict its permissions to only what's needed
