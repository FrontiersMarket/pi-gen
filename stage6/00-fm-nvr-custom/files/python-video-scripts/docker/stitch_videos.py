#!/usr/bin/env python3
import argparse
import os
import sys
import glob
import subprocess
import logging
from datetime import datetime, timedelta
from google.cloud import storage

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

def get_last_processed_file(lp_directory):
    """Read the pointer file to get the last processed file."""
    pointer_file = os.path.join(lp_directory, f"last-file-processed.txt")
    if os.path.exists(pointer_file):
        with open(pointer_file, 'r') as f:
            return f.read().strip()  # Return the last processed file
    return None  # If the pointer file does not exist, return None

def update_pointer_file(up_directory, last_file):
    """Write the name of the last processed file to the pointer file."""
    pointer_file = os.path.join(up_directory, f"last-file-processed.txt")
    with open(pointer_file, 'w') as f:
        f.write(last_file)

def find_segments(directory, gcs_bucket_name, prefix=None, start_date=None, end_date=None):
    """Find all video segments matching criteria."""
    # Convert date strings to datetime objects if provided
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)  # Include the entire end date

    # Get all .ts files
    pattern = os.path.join(directory, f"{prefix+'_' if prefix else ''}*.ts")
    files = glob.glob(pattern)


    # Testing Cloud SDK
    #client = storage.Client()
    #bucket = client.bucket(gcs_bucket_name)

    # List all objects with the prefix (acts like a folder filter)
    #if directory:
    #    prefix = directory if directory.endswith("/") else directory + "/"
    #    blobs = list(bucket.list_blobs(prefix=prefix))
    #else:
    #    blobs = list(bucket.list_blobs())

    # Print file names
    #files = [blob.name for blob in blobs if blob.name.endswith(".ts")]

    #files = [f"gs://{gcs_bucket_name}/{blob.name}" for blob in blobs]


    # Filter and sort files
    filtered_files = []
    for file in files:
        timestamp = parse_timestamp(file)
        if not timestamp:
            continue
            
        if start_date and timestamp < start_date:
            continue
        if end_date and timestamp >= end_date:
            continue
        
        #print(f"TS: {timestamp} {file}")
        filtered_files.append((timestamp, file))
    
    # Sort by timestamp
    filtered_files.sort()
    return [f for _, f in filtered_files]

def has_video_stream(file_path):
    """Check if a file contains a video stream using ffprobe."""
    #print(f"VS: {file_path}")

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

def create_concat_file(files, concat_file, up_directory, batchsize):
    """Create FFmpeg concat file."""
    with open(concat_file, 'w') as f:

        last_processed_file = get_last_processed_file(up_directory)
        start_processing = False
        #print(f"LF: {last_processed_file}")

        if last_processed_file is None:
            files_to_process = files[:500]  # Get only the first 500 files
        else:
            files_to_process = files  # Process all files

        if batchsize and int(batchsize) > 0:
            set_batchsize = 1
            bcount = 0

        for video_file in files_to_process:

            bn_video_file = os.path.basename(video_file)
            #print(f"Processing {video_file}")

            # If we have found the last processed file, start processing next files
            if not start_processing and last_processed_file:
                #print (f"Skipped: {bn_video_file}")

                if bn_video_file == last_processed_file:
                      start_processing = True
                continue
                #print(f"Processing: {bn_video_file}")

            if has_video_stream(video_file):
                f.write(f"file '{video_file}'\n")

                #print(f"File kept")
            else:
                print(f"File skipped: {video_file}")

            if set_batchsize == 1:
                bcount += 1
                if bcount >= int(batchsize):
                    print(f"Batchsize of {batchsize} reached")
                    break

        update_pointer_file(up_directory, bn_video_file)

def stream_ffmpeg_to_gcs(ff_concat_file, bucket_name, destination_blob_name, f_filename, l_filename):
    """Runs FFmpeg and streams the output directly to GCS."""
    # Generate timestamp
    ftimestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    sfilename = "stitched_video"

    if destination_blob_name:
        dest_blob_name = destination_blob_name.rstrip("/")
        fin_dest_blob_name = f"{dest_blob_name}/{sfilename}_{ftimestamp}_{f_filename}_to_{l_filename}.mp4"
    else:
        fin_dest_blob_name = f"{sfilename}_{ftimestamp}_{f_filename}_to_{l_filename}.mp4"

    # Initialize GCS client
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(fin_dest_blob_name)

    # Construct FFmpeg command with progress and error handling
    ffmpeg_cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', ff_concat_file,
        '-map', '0:v',
        '-c', 'copy',
        '-movflags', '+frag_keyframe+empty_moov+faststart',
        '-f', 'mp4',
        'pipe:1'
    ]

    with blob.open("wb") as gcs_stream:
        # Run FFmpeg and stream output
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**6)
        for chunk in iter(lambda: process.stdout.read(4096), b""):
            gcs_stream.write(chunk)

        process.wait()
        if process.returncode == 0:
            print(f"Successfully streamed to gs://{bucket_name}/{destination_blob_name}")
        else:
            print("FFmpeg processing failed", process.stderr.read().decode())

def stitch_videos(input_dir, output_file, gcs_bucket, batchsize, prefix=None, start_date=None, end_date=None, timeout=3600):
    """Stitch video segments together.
    Args:
        input_dir: Directory containing video segments
        output_file: Path to output stitched video
        gcs_bucket: Which GCS bucket to use, for Cloud SDK (experimental)
        batchsize: Max number of files to process per batch
        prefix: Optional prefix to filter segments
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
        timeout: Maximum time in seconds to wait for stitching (default: 5 minutes)
    Returns:
        bool: True if successful, False otherwise
    """

    # Find and filter segments
    #print(f"Find segments")
    segments = find_segments(input_dir, gcs_bucket, prefix, start_date, end_date)
    if not segments:
        logging.error("No video segments found matching criteria")
        return False

    # Create temporary concat file
    #print(f"Create concat file")
    concat_file = f'concat_list_{os.getpid()}.txt'
    create_concat_file(segments, concat_file, input_dir, batchsize)

    #print(f"Verify segments and concat file")
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

        with open(concat_file, "r") as file:
            contents = file.read()
            print(f"View concat list")
            print(contents)

        if os.path.exists(concat_file) and not os.stat(concat_file).st_size == 0:

            first_file = None
            last_file = None
            with open(concat_file, "r") as f:
                for line in f:
                    if first_file is None:
                        first_file = line.strip()  # First line
                    last_file = line.strip()  # Last line (updated each iteration)

            p_first_file = parse_timestamp(first_file)
            f_first_file = p_first_file.strftime("%Y%m%d_%H%M%S")
            p_last_file = parse_timestamp(last_file)
            f_last_file = p_last_file.strftime("%Y%m%d_%H%M%S")

            #print(f"F; {f_first_file} / L: {f_last_file}")


            # SDK not working forvery large files
            #stream_ffmpeg_to_gcs(concat_file, gcs_bucket, output_file, f_first_file, f_last_file)


            # Generate timestamp
            ftimestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            sfilename = "stitched_video"

            new_output_file = f"{sfilename}_{ftimestamp}_{f_first_file}_to_{f_last_file}.mp4"

            # Extract directory and join with new filename
            base_directory = os.path.dirname(output_file)
            fin_output_file = os.path.join(base_directory, new_output_file)

            # Create output directory
            output_dir = os.path.dirname(fin_output_file)
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
                '-movflags', '+frag_keyframe+empty_moov+faststart',  # Optimize for web playback
                '-progress', 'pipe:1',   # Show progress
                '-y',                   # Overwrite output
                fin_output_file
            ]

            # Run FFmpeg with timeout
            logging.info(f"Stitching valid segments into {fin_output_file}")
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
                if not os.path.exists(fin_output_file) or os.path.getsize(fin_output_file) == 0:
                    logging.error("Output file is missing or empty")
                    return False

                logging.info(f"Successfully stitched video: {fin_output_file}")
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
    parser.add_argument('--output', required=True, help='Output file path, gcs root or subdir')
    parser.add_argument('--gcs-bucket', required=True, help='GCS Bucket for output files')
    parser.add_argument('--batchsize', help='Optional max number of files to process per batch')
    parser.add_argument('--prefix', help='Optional prefix to filter segments')
    parser.add_argument('--start-date', help='Optional start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='Optional end date (YYYY-MM-DD)')
    parser.add_argument('--timeout', type=int, default=3600, help='Timeout in seconds (default: 3600)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s')
    
    success = stitch_videos(
        args.input_dir,
        args.output,
        args.gcs_bucket,
        args.batchsize,
        args.prefix,
        args.start_date,
        args.end_date,
        args.timeout
    )
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
