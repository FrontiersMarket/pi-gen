#!/usr/bin/env python3
import os
import sys
import glob
import subprocess
import logging
import tempfile
from datetime import datetime, timedelta
from flask import Flask, request
from google.cloud import storage

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def parse_timestamp(filename):
    """Extract timestamp from filename pattern: prefix_YYYYMMDD_HHMMSS.ts"""
    try:
        parts = os.path.splitext(filename)[0].split('_')
        if len(parts) < 2:
            raise ValueError("Filename does not contain enough parts")
        date_time_str = '_'.join(parts[-2:])
        return datetime.strptime(date_time_str, '%Y%m%d_%H%M%S')
    except (IndexError, ValueError) as e:
        logging.warning(f"Could not parse timestamp from filename: {filename}")
        return None

def create_concat_file(files, concat_file):
    """Create FFmpeg concat file."""
    with open(concat_file, 'w') as f:
        for _, file in files:
            f.write(f"file '{file}'\n")

def download_segments(bucket_name, prefix, date, temp_dir):
    """Download video segments for the specified date from GCS."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    
    # Convert date to datetime for comparison
    target_date = datetime.strptime(date, '%Y-%m-%d')
    next_date = target_date + timedelta(days=1)
    
    downloaded_files = []
    # List all blobs with the prefix
    blobs = bucket.list_blobs(prefix=prefix)
    for blob in blobs:
        # Skip non-ts files
        if not blob.name.endswith('.ts'):
            continue
            
        # Parse timestamp from filename
        timestamp = parse_timestamp(os.path.basename(blob.name))
        if not timestamp:
            continue
            
        # Check if file is from the target date
        if target_date <= timestamp < next_date:
            # Download to temp directory
            local_path = os.path.join(temp_dir, os.path.basename(blob.name))
            blob.download_to_filename(local_path)
            downloaded_files.append((timestamp, local_path))
    
    return sorted(downloaded_files)

def stitch_videos(files, output_file):
    """Stitch video segments together."""
    if not files:
        raise ValueError("No files to stitch")
    
    # Create temporary concat file
    concat_file = output_file + '.txt'
    create_concat_file(files, concat_file)
    
    # Build FFmpeg command
    cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file,
        '-c', 'copy',
        output_file
    ]
    
    # Run FFmpeg
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg error: {e.stderr}")
        return False
    finally:
        # Clean up concat file
        if os.path.exists(concat_file):
            os.remove(concat_file)

def upload_stitched_video(bucket_name, source_file, destination_blob_name):
    """Upload stitched video to GCS."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    
    blob.upload_from_filename(source_file)
    return blob.public_url

@app.route('/stitch', methods=['POST'])
def stitch_handler():
    """Handle video stitching requests."""
    request_json = request.get_json(silent=True)
    if not request_json:
        return {'error': 'No JSON data received'}, 400
    
    # Get parameters
    bucket_name = request_json.get('bucket')
    prefix = request_json.get('prefix')
    date = request_json.get('date')
    
    if not all([bucket_name, prefix, date]):
        return {'error': 'Missing required parameters'}, 400
    
    try:
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download segments
            logging.info(f"Downloading segments for {date}")
            files = download_segments(bucket_name, prefix, date, temp_dir)
            
            if not files:
                return {'error': f'No video segments found for {date}'}, 404
            
            # Create output filename
            output_file = os.path.join(temp_dir, f"{prefix}_{date}.mp4")
            
            # Stitch videos
            logging.info(f"Stitching {len(files)} segments")
            if not stitch_videos(files, output_file):
                return {'error': 'Failed to stitch videos'}, 500
            
            # Upload result
            logging.info("Uploading stitched video")
            destination_blob = f"stitched/{prefix}_{date}.mp4"
            public_url = upload_stitched_video(bucket_name, output_file, destination_blob)
            
            return {
                'success': True,
                'url': public_url,
                'segments_processed': len(files)
            }
            
    except Exception as e:
        logging.exception("Error processing request")
        return {'error': str(e)}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
