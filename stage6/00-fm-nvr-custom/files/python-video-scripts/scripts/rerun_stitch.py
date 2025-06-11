#!/usr/bin/env python3
import os
import sys
import logging
from test_video_integrity import stitch_and_verify, compare_results

def main():
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
    
    # Get segments directory
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    segments_dir = os.path.join(base_dir, "output", "segments")
    stitched_dir = os.path.join(base_dir, "output", "stitched")
    
    # Create list of recordings from existing directories
    recordings = []
    for entry in os.listdir(segments_dir):
        if entry.startswith("duration_"):
            parts = entry.split("_")
            duration = int(parts[1])
            segment_size = int(parts[3])
            recordings.append({
                'duration': duration,
                'segment_size': segment_size,
                'directory': os.path.join(segments_dir, entry),
                'prefix': f"test_{duration}_{segment_size}"
            })
    
    if not recordings:
        logging.error("No recording directories found in %s", segments_dir)
        sys.exit(1)
    
    # Stitch and verify
    logging.info("Stitching segments and verifying integrity...")
    results = stitch_and_verify(recordings, stitched_dir)
    
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
