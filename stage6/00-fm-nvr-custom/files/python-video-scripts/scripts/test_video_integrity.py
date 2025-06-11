#!/usr/bin/env python3
import os
import sys
import json
import logging
import subprocess
import tempfile
import hashlib
from datetime import datetime, timedelta
import argparse
from pathlib import Path

def get_video_info(video_path):
    """Get video metadata using ffprobe."""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error getting video info: {e.stderr}")
        return None

def compute_video_hash(video_path):
    """Compute video hash that ignores metadata but captures content."""
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-map', '0:v:0',  # Take only first video stream
        '-c', 'copy',     # No re-encoding
        '-f', 'md5',      # Output MD5 hash
        '-'               # Output to stdout
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # FFmpeg outputs: MD5=hash
        return result.stdout.strip().split('=')[1]
    except subprocess.CalledProcessError as e:
        logging.error(f"Error computing video hash: {e.stderr}")
        return None

import multiprocessing
import signal

def run_single_recording(rtsp_url, test_dir, segment_size, prefix, duration):
    """Run a single recording process."""
    cmd = [
        'python3', 'rtsp_streamer.py',
        '--rtsp_url', rtsp_url,
        '--output_dir', test_dir,
        '--segment_time', str(segment_size),
        '--file_prefix', prefix,
        '--max-duration', str(duration)
    ]
    
    try:
        subprocess.run(cmd, check=True)
        return {
            'duration': duration,
            'segment_size': segment_size,
            'directory': test_dir,
            'prefix': prefix,
            'success': True
        }
    except subprocess.CalledProcessError as e:
        logging.error(f"Error recording segments: {e}")
        return {
            'duration': duration,
            'segment_size': segment_size,
            'directory': test_dir,
            'prefix': prefix,
            'success': False
        }

def record_test_segments(rtsp_url, output_dir, durations, segment_sizes):
    """Record multiple sets of segments with different segment sizes in parallel."""
    processes = []
    recordings = []
    max_duration = max(durations)
    
    # Create a process pool
    with multiprocessing.Pool() as pool:
        tasks = []
        
        # Start all recordings simultaneously
        for duration in durations:
            for segment_size in segment_sizes:
                test_dir = os.path.join(output_dir, f"duration_{duration}_segment_{segment_size}")
                os.makedirs(test_dir, exist_ok=True)
                prefix = f"test_{duration}_{segment_size}"
                
                # Add task to pool
                task = pool.apply_async(run_single_recording, 
                    (rtsp_url, test_dir, segment_size, prefix, duration))
                tasks.append(task)
        
        # Wait for all tasks to complete
        for task in tasks:
            result = task.get(timeout=max_duration + 60)  # Add 60s buffer
            if result['success']:
                recordings.append(result)
    
    return recordings

def stitch_and_verify(recordings, output_dir):
    """Stitch each recording and verify integrity."""
    results = []
    max_duration = max(r['duration'] for r in recordings)
    stitch_timeout = max_duration + 60  # Add 60s buffer for stitching
    
    for rec in recordings:
        output_file = os.path.join(output_dir, f"stitched_{rec['duration']}_{rec['segment_size']}.mp4")
        logging.info(f"\nProcessing recording: duration={rec['duration']}s, segment_size={rec['segment_size']}s")
        
        # Import stitch_videos dynamically to get the latest version
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "stitch_videos", 
            os.path.join(os.path.dirname(__file__), "stitch_videos.py")
        )
        stitch_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stitch_module)
        
        try:
            # Stitch segments with timeout
            success = stitch_module.stitch_videos(
                input_dir=rec['directory'],
                output_file=output_file,
                prefix=rec['prefix'],
                timeout=stitch_timeout
            )
            
            if not success:
                logging.error(f"Failed to stitch video: {output_file}")
                continue
            
            # Get video info
            info = get_video_info(output_file)
            if not info:
                logging.error(f"Failed to get video info: {output_file}")
                continue
                
            # Compute content hash
            content_hash = compute_video_hash(output_file)
            if not content_hash:
                logging.error(f"Failed to compute hash: {output_file}")
                continue
                
            logging.info(f"Successfully processed: {os.path.basename(output_file)}")
            results.append({
                'file': output_file,
                'duration': rec['duration'],
                'segment_size': rec['segment_size'],
                'info': info,
                'hash': content_hash
            })
            
        except Exception as e:
            logging.error(f"Error processing video: {e}")
            continue
    
    if not results:
        logging.error("No videos were successfully stitched and verified")
    
    return results

def compare_results(results):
    """Compare video metadata and hashes across different segmentation strategies.
    All videos should be identical since they were recorded simultaneously."""
    if not results:
        logging.error("No results to compare")
        return False
    
    success = True
    base = results[0]
    base_duration = float(base['info']['format']['duration'])
    base_hash = base['hash']
    
    logging.info("\nBase video: %s", os.path.basename(base['file']))
    logging.info("Duration: %.2f seconds", base_duration)
    logging.info("Hash: %s", base_hash)
    
    mismatches = []
    for other in results[1:]:
        current_file = os.path.basename(other['file'])
        logging.info("\nComparing with: %s", current_file)
        
        # Compare duration (allow 1 second difference)
        other_duration = float(other['info']['format']['duration'])
        logging.info("Duration: %.2f seconds", other_duration)
        if abs(base_duration - other_duration) > 1.0:
            msg = f"Duration mismatch: {base_duration:.2f} vs {other_duration:.2f} seconds"
            logging.error(msg)
            mismatches.append((current_file, msg))
            success = False
        
        # Compare content hash
        other_hash = other['hash']
        logging.info("Hash: %s", other_hash)
        if other_hash != base_hash:
            msg = f"Content hash mismatch\nExpected: {base_hash}\nGot: {other_hash}"
            logging.error(msg)
            mismatches.append((current_file, msg))
            success = False
    
    if mismatches:
        logging.error("\nSummary of mismatches:")
        for file, error in mismatches:
            logging.error("\n%s:\n%s", file, error)
    else:
        logging.info("\nAll videos are identical!")
        
        for other in group[1:]:
            # Compare durations (allow 0.1 second difference)
            other_duration = float(other['info']['format']['duration'])
            if abs(base_duration - other_duration) > 0.1:
                logging.error(
                    f"Duration mismatch: {base['file']} ({base_duration:.2f}s) vs "
                    f"{other['file']} ({other_duration:.2f}s)"
                )
                success = False
            
            # Compare content hashes
            if base_hash != other['hash']:
                logging.error(
                    f"Content hash mismatch: {base['file']} vs {other['file']}\n"
                    f"Base hash: {base_hash}\n"
                    f"Other hash: {other['hash']}"
                )
                success = False
            else:
                logging.info(
                    f"Videos match: {base['file']} ({base['segment_size']}s segments) vs "
                    f"{other['file']} ({other['segment_size']}s segments)"
                )
    
    return success

def main():
    parser = argparse.ArgumentParser(description='Test video segmentation and stitching integrity')
    parser.add_argument('--rtsp-url', required=True, help='RTSP URL to record from')
    parser.add_argument('--output-dir', required=True, help='Output directory for test files')
    parser.add_argument('--durations', type=int, nargs='+', default=[60, 120],
                       help='Recording durations to test (seconds)')
    parser.add_argument('--segment-sizes', type=int, nargs='+', default=[10, 30, 60],
                       help='Segment sizes to test (seconds)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s')
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Record test segments
    logging.info("Recording test segments...")
    recordings = record_test_segments(
        args.rtsp_url,
        os.path.join(args.output_dir, "segments"),
        args.durations,
        args.segment_sizes
    )
    
    if not recordings:
        logging.error("No recordings were successful")
        sys.exit(1)
    
    # Stitch and verify
    logging.info("Stitching segments and verifying integrity...")
    results = stitch_and_verify(recordings, os.path.join(args.output_dir, "stitched"))
    
    # Compare results
    logging.info("Comparing results...")
    success = compare_results(results)
    
    if success:
        logging.info("All tests passed successfully!")
        sys.exit(0)
    else:
        logging.error("Some tests failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
