#!/usr/bin/env python3
import argparse
import os
import sys
import glob
import subprocess
import logging
from datetime import datetime, timedelta

def parse_timestamp(filename):
    """Extract timestamp from filename pattern: prefix_YYYYMMDD_HHMMSS.ts"""
    try:
        # Extract date and time portion from the last two segments
        parts = os.path.splitext(filename)[0].split('_')
        if len(parts) < 2:
            raise ValueError("Filename does not contain enough parts")
        date_time_str = '_'.join(parts[-2:])  # Take last two parts for date and time
        return datetime.strptime(date_time_str, '%Y%m%d_%H%M%S')
    except (IndexError, ValueError) as e:
        logging.warning(f"Could not parse timestamp from filename: {filename}")
        return None

def find_segments(directory, prefix=None, start_date=None, end_date=None):
    """Find all video segments matching criteria."""
    # Convert date strings to datetime objects if provided
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)  # Include the entire end date

    # Get all .ts files
    pattern = os.path.join(directory, f"{prefix+'_' if prefix else ''}*.ts")
    files = glob.glob(pattern)
    
    # Filter and sort files
    filtered_files = []
    for file in files:
        filename = os.path.basename(file)
        timestamp = parse_timestamp(filename)
        if not timestamp:
            continue
            
        if start_date and timestamp < start_date:
            continue
        if end_date and timestamp >= end_date:
            continue
            
        filtered_files.append((timestamp, file))
    
    # Sort by timestamp
    filtered_files.sort()
    return [f for _, f in filtered_files]

def has_video_stream(file_path):
    """Check if a file contains a video stream using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-i", file_path, "-show_streams", "-select_streams", "v", "-loglevel", "error"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return bool(result.stdout.strip())
    except Exception as e:
        logging.error(f"Error checking video stream for {file_path}: {e}")
        return False

def create_concat_file(files, concat_file):
    """Create FFmpeg concat file."""
    with open(concat_file, 'w') as f:
        for video_file in files:

            if has_video_stream(os.path.abspath(video_file)):
                f.write(f"file '{os.path.abspath(video_file)}'\n")

def stitch_videos(input_dir, output_file, prefix=None, start_date=None, end_date=None, timeout=300):
    """Stitch video segments together.
    Args:
        input_dir: Directory containing video segments
        output_file: Path to output stitched video
        prefix: Optional prefix to filter segments
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
        timeout: Maximum time in seconds to wait for stitching (default: 5 minutes)
    Returns:
        bool: True if successful, False otherwise
    """
    # Find and filter segments
    segments = find_segments(input_dir, prefix, start_date, end_date)
    if not segments:
        logging.error("No video segments found matching criteria")
        return False

    # Create temporary concat file
    concat_file = f'concat_list_{os.getpid()}.txt'
    create_concat_file(segments, concat_file)

    try:
        # Verify all segments exist and are readable
        missing_segments = []
        for i, segment in enumerate(segments):
            if not os.path.exists(segment):
                missing_segments.append((i+1, segment))
            elif not os.access(segment, os.R_OK):
                missing_segments.append((i+1, f"{segment} (not readable)"))
        
        if missing_segments:
            for i, segment in missing_segments:
                logging.error(f"Segment {i} issue: {segment}")
            return False

        # Verify concat file
        if not os.path.exists(concat_file):
            logging.error(f"Concat file not found: {concat_file}")
            return False

        # Create output directory
        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Construct FFmpeg command with progress and error handling
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-map', '0:v',
            '-c', 'copy',           # Direct stream copy, no re-encoding
            '-movflags', '+faststart',  # Optimize for web playback
            '-progress', 'pipe:1',   # Show progress
            '-y',                   # Overwrite output
            output_file
        ]

        # Run FFmpeg with timeout
        logging.info(f"Stitching {len(segments)} segments into {output_file}")
        logging.debug(f"FFmpeg command: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout)
            if process.returncode != 0:
                logging.error(f"FFmpeg failed with error:\n{stderr}")
                return False
            
            # Verify output file exists and has size > 0
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                logging.error("Output file is missing or empty")
                return False

            logging.info(f"Successfully stitched video: {output_file}")
            return True

        except subprocess.TimeoutExpired:
            process.kill()
            logging.error(f"Stitching timed out after {timeout} seconds")
            return False
    finally:
        # Clean up concat file
        try:
            if os.path.exists(concat_file):
                os.remove(concat_file)
        except Exception as e:
            logging.warning(f"Failed to remove concat file: {e}")

        except Exception as e:
            logging.error(f"Error during stitching: {e}")
            return False
        finally:
            # Clean up concat file
            try:
                if os.path.exists(concat_file):
                    os.remove(concat_file)
            except Exception as e:
                logging.warning(f"Failed to remove concat file: {e}")
    return True


def main():
    parser = argparse.ArgumentParser(description='Stitch video segments together.')
    parser.add_argument('--input-dir', required=True, help='Input directory containing video segments')
    parser.add_argument('--output', required=True, help='Output file path')
    parser.add_argument('--prefix', help='Optional prefix to filter segments')
    parser.add_argument('--start-date', help='Optional start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='Optional end date (YYYY-MM-DD)')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout in seconds (default: 300)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s')
    
    success = stitch_videos(
        args.input_dir,
        args.output,
        args.prefix,
        args.start_date,
        args.end_date,
        args.timeout
    )
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()



    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s')

    # Ensure input directory exists
    if not os.path.isdir(args.input_dir):
        logging.error(f"Input directory does not exist: {args.input_dir}")
        sys.exit(1)

    # Ensure output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Stitch videos
    success = stitch_videos(
        args.input_dir,
        args.output,
        args.prefix,
        args.start_date,
        args.end_date
    )

    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
