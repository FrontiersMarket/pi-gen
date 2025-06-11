#!/usr/bin/env python3
import argparse
import configparser
import os
import subprocess
import time
import logging
import re
from datetime import datetime


def get_ffmpeg_version():
    """Get the FFmpeg version installed on the system."""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              text=True)
        version_match = re.search(r'ffmpeg version (\d+\.\d+)', 
                                result.stdout)
        if version_match:
            return float(version_match.group(1))
    except (subprocess.SubprocessError, ValueError):
        logging.warning("Could not determine FFmpeg version, assuming older version")
    return 0.0


def build_ffmpeg_command(rtsp_url, output_dir, segment_time, file_prefix, config):
    """Build FFmpeg command based on version and configuration.
    
    Returns:
        tuple: (list, str) - FFmpeg command as list of arguments and the output directory
    """
    transport = config.get('transport_protocol', 'tcp').lower()
    socket_timeout = int(config.get('socket_timeout', 5))
    reconnect_delay = int(config.get('reconnect_delay_seconds', 5))
    max_reconnect_delay = int(config.get('max_reconnect_delay_seconds', 30))
    ffmpeg_version = float(config.get('ffmpeg_version', get_ffmpeg_version()))
    legacy_mode = config.get('force_legacy_mode', 'false').lower() == 'true'
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    # Base pattern for output files - write directly to output_dir
    pattern = os.path.join(output_dir, f"{file_prefix}_%Y%m%d_%H%M%S.ts")
    
    cmd = ['ffmpeg']
    
    # Add version-specific and mode-specific options
    if ffmpeg_version >= 8.0 and not legacy_mode:
        cmd.extend([
            '-rtsp_transport', transport,
            '-stimeout', str(socket_timeout * 1000000),  # Socket timeout in microseconds
            '-reconnect', '1',
            '-reconnect_at_eof', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', str(max_reconnect_delay),
        ])
    else:
        # Legacy mode for older FFmpeg versions
        cmd.extend([
            '-rtsp_transport', transport,
            '-timeout', str(socket_timeout)  # Basic timeout in seconds
        ])
    
    # Add TCP-specific flags if using TCP
    if transport == 'tcp':
        cmd.extend(['-rtsp_flags', 'prefer_tcp'])
    
    # Input options
    cmd.extend([
        '-i', rtsp_url,
    ])
    
    # Output options for reliable streaming
    cmd.extend([
        '-c', 'copy',                    # Direct stream copy, no re-encoding
        '-f', 'segment',                 # Segment the stream
        '-segment_time', str(segment_time),
        '-segment_atclocktime', '1',     # Align segments with wall clock
        '-strftime', '1',                # Use strftime in filename
        '-reset_timestamps', '1',        # Reset timestamps at segment boundaries
        '-segment_format', 'mpegts',     # Use MPEG-TS format for better compatibility
        '-segment_list', os.path.join(output_dir, 'segments.txt'),  # Keep track of segments
        '-segment_list_flags', '+live',  # Update segment list as we go
        '-copyts',                       # Copy timestamps from input
        '-start_at_zero',                # Ensure first segment starts at 0
        '-avoid_negative_ts', '1',       # Keep negative timestamps
    ])
    
    # Error handling and recovery options
    cmd.extend([
        '-err_detect', 'aggressive',     # Aggressive error detection
        '-fflags', '+genpts+igndts',    # Generate presentation timestamps, ignore decode timestamps
    ])
    
    # Output pattern
    cmd.append(pattern)
    
    return cmd, output_dir


def start_stream(rtsp_url, output_dir, segment_time, file_prefix, config):
    """Start ffmpeg process to stream RTSP video into segments while maintaining original format.
    Handles different FFmpeg versions and provides improved error recovery."""
    cmd, base_dir = build_ffmpeg_command(rtsp_url, output_dir, segment_time, file_prefix, config)
    
    logging.info("Starting RTSP stream from %s, saving segments to %s", rtsp_url, base_dir)
    logging.debug("FFmpeg command: %s", ' '.join(cmd))
    
    process = subprocess.Popen(cmd, 
                             stdout=subprocess.PIPE, 
                             stderr=subprocess.PIPE,
                             universal_newlines=True,
                             bufsize=1)
    
    return process, base_dir


def monitor_stream(rtsp_url, output_dir, segment_time, sleep_interval, file_prefix, config=None):
    """Continuously monitor the RTSP stream process and restart if it stops.
    Implements improved error handling and segment management."""
    if config is None:
        config = {}
    
    consecutive_failures = 0
    max_sleep = int(config.get('max_retry_interval', 60))  # Maximum sleep time in seconds
    max_retries = int(config.get('max_retries', 0))  # 0 means infinite retries
    max_segment_size = int(config.get('max_segment_size_mb', 500)) * 1024 * 1024  # Convert to bytes
    max_duration = int(config.get('max_duration', 0))  # Maximum duration in seconds (0 = infinite)
    start_time = time.time()
    
    while True:
        try:
            process, current_dir = start_stream(rtsp_url, output_dir, segment_time, file_prefix, config)
            
            # Monitor the process output and segment sizes
            while process.poll() is None:
                # Check duration limit
                if max_duration > 0 and (time.time() - start_time) >= max_duration:
                    logging.info("Reached maximum duration of %d seconds", max_duration)
                    process.terminate()
                    return  # Exit the function completely
                
                stderr_line = process.stderr.readline()
                if stderr_line:
                    stderr_line = stderr_line.strip()
                    # Common RTSP/network errors that indicate temporary issues
                    temp_errors = ['Connection refused', 'Connection timed out', 'Network is unreachable',
                                  'End of file', 'Immediate exit requested', 'Invalid data']
                    
                    if any(err in stderr_line for err in temp_errors):
                        logging.warning("Temporary network error: %s", stderr_line)
                        # Use exponential backoff for network issues
                        sleep_time = min(consecutive_failures * 2, max_sleep)
                        logging.info("Waiting %d seconds before retry...", sleep_time)
                        process.terminate()
                        time.sleep(sleep_time)
                        consecutive_failures += 1
                        break
                    elif 'Error' in stderr_line:
                        logging.error("FFmpeg error detected: %s", stderr_line)
                        # Force a new segment on error
                        process.terminate()
                        # Clean up potentially corrupted segment
                        for f in os.listdir(output_dir):
                            if f.endswith('.ts'):
                                f_path = os.path.join(output_dir, f)
                                # Check if file was modified in the last few seconds
                                if time.time() - os.path.getmtime(f_path) < 5:
                                    # Check if file is empty or very small
                                    if os.path.getsize(f_path) < 1024:
                                        logging.warning("Removing corrupted segment: %s", f)
                                        os.remove(f_path)
                        break
                    
                    # Log FFmpeg output at debug level
                    logging.debug("FFmpeg: %s", stderr_line.strip())
                
                # Check segment sizes
                for segment in os.listdir(current_dir):
                    if segment.endswith('.ts'):
                        segment_path = os.path.join(current_dir, segment)
                        try:
                            if os.path.getsize(segment_path) > max_segment_size:
                                logging.warning("Segment %s exceeded maximum size. Starting new segment.", segment)
                                # Force a new segment
                                process.terminate()
                                break
                        except OSError as e:
                            logging.error("Error checking segment size: %s", e)
                
                time.sleep(1)  # Prevent CPU overuse
            
            # Process has ended, check the return code
            return_code = process.poll()
            stderr_output = process.stderr.read()
            
            if return_code != 0:
                error_msg = stderr_output.strip()
                logging.error("FFmpeg process terminated with error (code %d): %s", return_code, error_msg)
                consecutive_failures += 1
                
                # Check if we've exceeded max retries
                if max_retries > 0 and consecutive_failures > max_retries:
                    logging.error("Exceeded maximum retries (%d). Stopping stream monitor.", max_retries)
                    break
            else:
                consecutive_failures = 0
                
        except Exception as e:
            logging.exception("Error in stream process: %s", e)
            consecutive_failures += 1
            
            # Check if we've exceeded max retries
            if max_retries > 0 and consecutive_failures > max_retries:
                logging.error("Exceeded maximum retries (%d). Stopping stream monitor.", max_retries)
                break
        
        # Calculate sleep time with exponential backoff
        sleep_time = min(sleep_interval * (2 ** consecutive_failures), max_sleep)
        logging.info("Restarting stream in %d seconds...", sleep_time)
        time.sleep(sleep_time)


def main():
    parser = argparse.ArgumentParser(description='Stream RTSP video to local disk in segmented files.')
    parser.add_argument('--rtsp_url', help='RTSP stream URL')
    parser.add_argument('--output_dir', help='Output directory for video segments')
    parser.add_argument('--segment_time', type=int, help='Segment duration in seconds (default: 600)')
    parser.add_argument('--sleep_interval', type=int, help='Sleep interval before restarting stream (default: 5)')
    parser.add_argument('--stream_name', help='Name of the stream configuration to use (e.g., front, back)')
    parser.add_argument('--file_prefix', help='Prefix for output files')
    
    # Optional advanced arguments
    parser.add_argument('--socket-timeout', type=int, help='Socket timeout in seconds')
    parser.add_argument('--max-retry-interval', type=int, help='Maximum retry interval in seconds')
    parser.add_argument('--transport-protocol', choices=['tcp', 'udp'], help='Transport protocol')
    parser.add_argument('--max-retries', type=int, help='Maximum number of retries (0 = infinite)')
    parser.add_argument('--max-duration', type=int, help='Maximum recording duration in seconds (0 = infinite)')

    args = parser.parse_args()

    # Load configuration from config.ini if available
    config_file = os.path.join(os.path.dirname(__file__), 'config.local.ini')
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        config.read(config_file)

    # Determine which stream config to use
    stream_section = None
    if args.stream_name:
        stream_section = f'Streamer.{args.stream_name}'
        if not config.has_section(stream_section):
            parser.error(f'Stream configuration {args.stream_name} not found in config file')
    else:
        # Find first available stream configuration
        for section in config.sections():
            if section.startswith('Streamer.'):
                stream_section = section
                break
        if not stream_section:
            parser.error('No stream configurations found in config file')

    # Load basic settings
    if not args.rtsp_url and config.has_option(stream_section, 'rtsp_url'):
        args.rtsp_url = config.get(stream_section, 'rtsp_url')
    if not args.output_dir and config.has_option(stream_section, 'output_dir'):
        args.output_dir = config.get(stream_section, 'output_dir')
    if not args.file_prefix and config.has_option(stream_section, 'file_prefix'):
        args.file_prefix = config.get(stream_section, 'file_prefix')
    if args.segment_time is None and config.has_option(stream_section, 'segment_time'):
        args.segment_time = config.getint(stream_section, 'segment_time')
    if args.sleep_interval is None and config.has_option(stream_section, 'sleep_interval'):
        args.sleep_interval = config.getint(stream_section, 'sleep_interval')

    # Load advanced settings
    advanced_config = {}
    if config.has_section(stream_section):
        # Socket timeout
        if args.socket_timeout is not None:
            advanced_config['socket_timeout'] = args.socket_timeout
        elif config.has_option(stream_section, 'socket_timeout'):
            advanced_config['socket_timeout'] = config.getint(stream_section, 'socket_timeout')
        else:
            advanced_config['socket_timeout'] = 5

        # Max retry interval
        if args.max_retry_interval is not None:
            advanced_config['max_retry_interval'] = args.max_retry_interval
        elif config.has_option(stream_section, 'max_retry_interval'):
            advanced_config['max_retry_interval'] = config.getint(stream_section, 'max_retry_interval')
        else:
            advanced_config['max_retry_interval'] = 60

        # Transport protocol
        if args.transport_protocol is not None:
            advanced_config['transport_protocol'] = args.transport_protocol
        elif config.has_option(stream_section, 'transport_protocol'):
            advanced_config['transport_protocol'] = config.get(stream_section, 'transport_protocol')
        else:
            advanced_config['transport_protocol'] = 'tcp'

        # Max retries
        if args.max_retries is not None:
            advanced_config['max_retries'] = args.max_retries
        elif config.has_option(stream_section, 'max_retries'):
            advanced_config['max_retries'] = config.getint(stream_section, 'max_retries')
        else:
            advanced_config['max_retries'] = 0
            
        # Max duration
        if args.max_duration is not None:
            advanced_config['max_duration'] = args.max_duration
        elif config.has_option(stream_section, 'max_duration'):
            advanced_config['max_duration'] = config.getint(stream_section, 'max_duration')
        else:
            advanced_config['max_duration'] = 0

    if not args.rtsp_url or not args.output_dir or not args.file_prefix:
        parser.error('rtsp_url, output_dir, and file_prefix must be provided via arguments or config file')

    # Set defaults for timing parameters
    if args.segment_time is None:
        args.segment_time = 600
    if args.sleep_interval is None:
        args.sleep_interval = 5

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

    try:
        monitor_stream(args.rtsp_url, args.output_dir, args.segment_time,
                      args.sleep_interval, args.file_prefix, advanced_config)
    except KeyboardInterrupt:
        logging.info("Stopping RTSP stream capture")


if __name__ == '__main__':
    main()
