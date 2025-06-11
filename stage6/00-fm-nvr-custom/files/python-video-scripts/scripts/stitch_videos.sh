#!/bin/bash

# This script provides a user-friendly interface for stitching video segments together

SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR"
cd .. # Move to project root

# Function to print usage
print_usage() {
    echo "Usage: $0 [options]"
    echo "Stitch video segments together into a single video file."
    echo
    echo "Options:"
    echo "  -i, --input-dir DIR    Directory containing video segments"
    echo "  -o, --output FILE      Output video file"
    echo "  -p, --prefix NAME      Stream prefix to filter (e.g., front_cam)"
    echo "  -s, --start-date DATE  Start date (YYYY-MM-DD)"
    echo "  -e, --end-date DATE    End date (YYYY-MM-DD)"
    echo "  -v, --verbose          Enable verbose output"
    echo "  -h, --help            Display this help message"
    echo
    echo "Example:"
    echo "  $0 -i ./test-data -o output.mp4 -p front_cam -s 2025-02-01 -e 2025-02-03"
}

# Parse command line arguments
POSITIONAL_ARGS=()
VERBOSE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--input-dir)
            INPUT_DIR="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT="$2"
            shift 2
            ;;
        -p|--prefix)
            PREFIX="$2"
            shift 2
            ;;
        -s|--start-date)
            START_DATE="$2"
            shift 2
            ;;
        -e|--end-date)
            END_DATE="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT" ]; then
    echo "Error: Input directory and output file are required"
    print_usage
    exit 1
fi

# Build command
CMD="python3 scripts/stitch_videos.py --input-dir \"$INPUT_DIR\" --output \"$OUTPUT\""
[ ! -z "$PREFIX" ] && CMD="$CMD --prefix \"$PREFIX\""
[ ! -z "$START_DATE" ] && CMD="$CMD --start-date \"$START_DATE\""
[ ! -z "$END_DATE" ] && CMD="$CMD --end-date \"$END_DATE\""
[ ! -z "$VERBOSE" ] && CMD="$CMD $VERBOSE"

# Run the command
echo "Stitching videos..."
eval $CMD

# Check result
if [ $? -eq 0 ]; then
    echo "Videos successfully stitched to: $OUTPUT"
else
    echo "Error stitching videos. Check the logs for details."
    exit 1
fi
