#!/usr/bin/env python3
import os
import sys
import json
import logging
import subprocess
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
        logging.error(f"Error getting video info for {video_path}: {e.stderr}")
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
        logging.error(f"Error computing video hash for {video_path}: {e.stderr}")
        return None

def analyze_video(video_path):
    """Analyze a single video file."""
    info = get_video_info(video_path)
    if not info:
        return None
        
    hash_value = compute_video_hash(video_path)
    if not hash_value:
        return None
        
    return {
        'path': video_path,
        'info': info,
        'hash': hash_value,
        'duration': float(info['format']['duration']),
        'size': int(info['format']['size'])
    }

def compare_videos(videos, tolerance_sec=0.1):
    """Compare a list of video files for content and duration matches."""
    if len(videos) < 2:
        logging.error("Need at least 2 videos to compare")
        return False
        
    base = videos[0]
    results = []
    
    for other in videos[1:]:
        duration_diff = abs(base['duration'] - other['duration'])
        hash_match = base['hash'] == other['hash']
        
        result = {
            'base_file': os.path.basename(base['path']),
            'compare_file': os.path.basename(other['path']),
            'duration_diff': duration_diff,
            'hash_match': hash_match,
            'base_duration': base['duration'],
            'compare_duration': other['duration'],
            'base_hash': base['hash'],
            'compare_hash': other['hash'],
            'base_size': base['size'],
            'compare_size': other['size']
        }
        
        results.append(result)
        
        # Log the comparison
        if hash_match:
            logging.info(f"✅ Content match: {result['base_file']} == {result['compare_file']}")
        else:
            logging.error(f"❌ Content mismatch: {result['base_file']} != {result['compare_file']}")
            
        if duration_diff <= tolerance_sec:
            logging.info(f"✅ Duration match: {result['base_file']} ({result['base_duration']:.2f}s) ≈ {result['compare_file']} ({result['compare_duration']:.2f}s)")
        else:
            logging.error(f"❌ Duration mismatch: {result['base_file']} ({result['base_duration']:.2f}s) != {result['compare_file']} ({result['compare_duration']:.2f}s)")
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Compare video files for content and duration matches')
    parser.add_argument('videos', nargs='+', help='Video files to compare')
    parser.add_argument('--tolerance', type=float, default=0.1,
                       help='Duration difference tolerance in seconds (default: 0.1)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--json', action='store_true',
                       help='Output results in JSON format')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s: %(message)s')
    
    # Analyze all videos
    video_data = []
    for video_path in args.videos:
        if not os.path.exists(video_path):
            logging.error(f"Video file not found: {video_path}")
            continue
            
        data = analyze_video(video_path)
        if data:
            video_data.append(data)
    
    if len(video_data) < 2:
        logging.error("Need at least 2 valid videos to compare")
        sys.exit(1)
    
    # Compare videos
    results = compare_videos(video_data, args.tolerance)
    
    # Output results
    if args.json:
        print(json.dumps(results, indent=2))
    
    # Determine exit code based on matches
    success = all(r['hash_match'] and r['duration_diff'] <= args.tolerance for r in results)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
