#!/usr/bin/env python3
import argparse
import os
import time
import logging
import hashlib
import base64
import configparser
import shutil
from pathlib import Path
from google.cloud import storage
from google.oauth2 import service_account


def compute_md5_base64(file_path):
    """Compute the MD5 checksum of a file and return it in base64 encoding."""
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    return base64.b64encode(md5.digest()).decode('utf-8')


def upload_file(bucket, file_path, destination_blob_name, config):
    """Upload a file to the given bucket using a resumable upload with a specified chunk size.
    Will retry on checksum failure and delete corrupted uploads.

    Returns:
        tuple: (success, md5_hash, error_msg)
            - success: bool indicating if upload was successful
            - md5_hash: the uploaded file's MD5 checksum if successful, None otherwise
            - error_msg: error message if upload failed, None otherwise
    """
    # Load configuration with defaults appropriate for low internet conditions
    max_retries = config.get('max_retries', 10)  # More retries for unstable connections
    chunk_size_mb = config.get('chunk_size_mb', 1)  # Smaller chunks by default
    chunk_size_bytes = int(chunk_size_mb * 1024 * 1024)  # Convert MB to bytes
    
    # Upload configuration
    upload_timeout = config.get('upload_timeout', 7200)  # 2 hour default timeout
    retry_max = config.get('retry_max', 10)  # More frequent retries
    retry_delay = config.get('retry_delay', 5)  # Short delay between retries
    retry_max_delay = config.get('retry_max_delay', 30)  # Cap maximum delay
    
    for attempt in range(max_retries):
        try:
            blob = bucket.blob(destination_blob_name)
            # Set the chunk size to use for resumable uploads
            blob.chunk_size = chunk_size_bytes
            logging.info('Uploading %s to bucket as %s (attempt %d/%d)', 
                        file_path, destination_blob_name, attempt + 1, max_retries)
            
            # Upload the file with resumable upload and configured timeout
            blob.upload_from_filename(
                file_path,
                timeout=None,
                if_generation_match=None,  # Allow resume of interrupted upload
                # retry_strategy=storage.RetryStrategy(
                #     max_retries=retry_max,
                #     initial_delay=retry_delay,
                #     maximum_delay=retry_max_delay,
                #     multiplier=1.5,  # Gentler backoff for unstable connections
                #     deadline=upload_timeout
                # )
            )
            # Reload to get the updated metadata including md5_hash
            blob.reload()
            
            # Verify the upload
            local_md5 = compute_md5_base64(file_path)
            if blob.md5_hash != local_md5:
                error_msg = f'Checksum mismatch (attempt {attempt + 1}): Local={local_md5}, GCS={blob.md5_hash}'
                logging.error(error_msg)
                # Delete the corrupted upload
                logging.info('Deleting corrupted upload: %s', destination_blob_name)
                blob.delete()
                if attempt < max_retries - 1:
                    continue
                return False, None, error_msg
            
            return True, blob.md5_hash, None
            
        except Exception as e:
            error_msg = f'Upload failed (attempt {attempt + 1}): {str(e)}'
            logging.error(error_msg)
            if attempt < max_retries - 1:
                continue
            return False, None, error_msg
    
    return False, None, 'Max retries exceeded'


def get_free_space_gb(directory):
    """Return free space in GB for the given directory's filesystem."""
    stats = shutil.disk_usage(directory)
    return stats.free / (1024 * 1024 * 1024)  # Convert bytes to GB


def ensure_directory_space(primary_dir, backup_dir, min_free_space_gb):
    """Check if primary directory has enough space, if not switch to backup.
    Returns the directory to use.
    
    Backup directory will only be used if:
    1. backup_dir is specified and not empty
    2. min_free_space_gb is greater than 0
    3. primary directory has less free space than min_free_space_gb
    """
    # Skip backup functionality if not properly configured
    if not backup_dir or not min_free_space_gb or min_free_space_gb <= 0:
        return primary_dir

    free_space = get_free_space_gb(primary_dir)
    if free_space < min_free_space_gb:
        logging.warning(
            f'Primary directory {primary_dir} has only {free_space:.2f}GB free space. '
            f'Checking backup directory {backup_dir}'
        )
        # Verify backup directory exists and is writable
        try:
            Path(backup_dir).mkdir(parents=True, exist_ok=True)
            # Test write permissions with a temporary file
            test_file = Path(backup_dir) / '.write_test'
            try:
                test_file.touch()
                test_file.unlink()  # Remove test file
                return backup_dir
            except (OSError, IOError) as e:
                logging.error(f'Backup directory {backup_dir} is not writable: {e}')
                return primary_dir
        except Exception as e:
            logging.error(f'Could not create/access backup directory {backup_dir}: {e}')
            return primary_dir

    return primary_dir


def monitor_and_upload(config):
    """Continuously monitor the directory for files that are stable, upload them to the bucket,
    verify the checksum, and delete the local file if the upload is successful."""
    # Setup GCS client
    if config.get('credentials_file'):
        credentials = service_account.Credentials.from_service_account_file(config['credentials_file'])
        client = storage.Client(credentials=credentials)
    else:
        client = storage.Client()
    bucket = client.bucket(config['bucket'])
    
    # Initialize report manager
    from uploader_report import UploaderReport
    report_manager = UploaderReport(config)
    
    # Create failed uploads directory
    failed_dir = os.path.join(config['directory'], 'failed_uploads')
    os.makedirs(failed_dir, exist_ok=True)
    
    # Keep track of failed uploads
    failed_uploads = {}
    
    while True:
        try:
            # Check directory space and switch if needed
            current_dir = ensure_directory_space(
                config['directory'],
                config.get('backup_directory'),
                config.get('min_free_space_gb', 0)
            )
            
            # Walk the directory recursively
            for root, dirs, files in os.walk(current_dir):
                # Skip failed uploads directory
                if root == failed_dir:
                    continue
                    
                for file in files:
                    file_path = os.path.join(root, file)
                    # Check if file last modified time is older than the threshold
                    mod_time = os.path.getmtime(file_path)
                    if time.time() - mod_time < config['file_age_threshold']:
                        continue

                    logging.info('Found file: %s', file_path)
                    # Handle empty or very small files (likely corrupted/incomplete)
                    file_size = os.path.getsize(file_path)
                    if file_size == 0 or file_size < 1024:  # Files smaller than 1KB
                        # Create zero_byte_files directory if it doesn't exist
                        zero_byte_dir = os.path.join(os.path.dirname(file_path), 'zero_byte_files')
                        os.makedirs(zero_byte_dir, exist_ok=True)
                        
                        # Move file to zero_byte_files directory
                        zero_byte_path = os.path.join(zero_byte_dir, os.path.basename(file_path))
                        logging.warning('Moving empty or too small file to zero_byte_files: %s (size: %d bytes)', file_path, file_size)
                        os.rename(file_path, zero_byte_path)
                        continue
                    
                    # Use the relative path as the destination blob name
                    destination_blob_name = os.path.relpath(file_path, config['directory'])
                    
                    # Upload with retries
                    success, uploaded_md5, error = upload_file(bucket, file_path, destination_blob_name, config)
                    
                    # Record upload attempt
                    report_manager.record_upload(
                        file_path,
                        destination_blob_name,
                        success,
                        os.path.getsize(file_path),
                        error
                    )
                    
                    if success:
                        # Double-check the MD5 hash before deleting
                        local_md5 = compute_md5_base64(file_path)
                        if uploaded_md5 == local_md5:
                            logging.info('Upload verified for %s (MD5: %s). Deleting the local file.', file_path, uploaded_md5)
                            os.remove(file_path)
                            # Clear any previous failure records
                            failed_uploads.pop(file_path, None)
                        else:
                            logging.error('Final MD5 verification failed for %s. Local=%s, Remote=%s', file_path, local_md5, uploaded_md5)
                            success = False
                            if file_path not in failed_uploads:
                                failed_uploads[file_path] = {'attempts': 0, 'first_failure': time.time()}
                            failed_uploads[file_path]['attempts'] += 1
                    else:
                        # Track failed upload
                        if file_path not in failed_uploads:
                            failed_uploads[file_path] = {'attempts': 0, 'first_failure': time.time()}
                        failed_uploads[file_path]['attempts'] += 1
                        
                        # If file has failed multiple times over a long period, move it to failed directory
                        if (failed_uploads[file_path]['attempts'] >= config.get('max_retries', 10) and 
                            time.time() - failed_uploads[file_path]['first_failure'] > config.get('upload_timeout', 7200)):
                            failed_path = os.path.join(failed_dir, os.path.basename(file_path))
                            logging.error(
                                'File %s has failed %d times over %d seconds. Moving to %s\nLast error: %s', 
                                file_path, 
                                failed_uploads[file_path]['attempts'],
                                time.time() - failed_uploads[file_path]['first_failure'],
                                failed_path,
                                error
                            )
                            shutil.move(file_path, failed_path)
                            del failed_uploads[file_path]
            
            # Check if we should generate a report
            if report_manager.should_generate_report():
                report_path = report_manager.generate_report()
                if report_path:
                    # Upload report to GCS
                    report_blob_name = os.path.join(
                        config.get('report_upload_prefix', 'reports'),
                        os.path.basename(report_path)
                    )
                    try:
                        success, _, error = upload_file(bucket, report_path, report_blob_name, config)
                        if success:
                            logging.info(f'Uploaded report: {report_blob_name}')
                            os.remove(report_path)
                        else:
                            logging.error(f'Failed to upload report: {error}')
                    except Exception as e:
                        logging.error(f'Error uploading report: {e}')
            
            time.sleep(config['sleep_interval'])
        except Exception as e:
            logging.exception('Error encountered: %s', e)
            time.sleep(config['sleep_interval'])


def main():
    parser = argparse.ArgumentParser(description='Continuously monitor a directory and upload files to a GCP bucket.')
    parser.add_argument('--config', default='config.local.ini', help='Path to config file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s:%(message)s')

    # Load configuration
    config_file = os.path.join(os.path.dirname(__file__), args.config)
    if not os.path.exists(config_file):
        parser.error(f'Config file not found: {config_file}')

    config = configparser.ConfigParser()
    config.read(config_file)

    if 'Uploader' not in config:
        parser.error('Config file must contain [Uploader] section')

    # Convert config to dict and set defaults
    uploader_config = dict(config['Uploader'])
    
    # Required settings
    required = ['directory', 'bucket']
    missing = [key for key in required if key not in uploader_config]
    if missing:
        parser.error(f'Missing required config options: {", ".join(missing)}')
    
    # Integer settings
    int_settings = [
        'file_age_threshold',
        'sleep_interval',
        'max_retries',
        'failed_upload_timeout',
        'inactivity_threshold',
        'upload_timeout',
        'retry_max',
        'retry_delay',
        'retry_max_delay'
    ]
    for key in int_settings:
        if key in uploader_config:
            uploader_config[key] = int(uploader_config[key])
    
    # Float settings
    float_settings = ['min_free_space_gb', 'chunk_size_mb']
    for key in float_settings:
        if key in uploader_config:
            uploader_config[key] = float(uploader_config[key])
    
    # Boolean settings
    bool_settings = ['daily_report_enabled']
    for key in bool_settings:
        if key in uploader_config:
            uploader_config[key] = config['Uploader'].getboolean(key)
    
    # Set defaults for optional settings
    defaults = {
        'file_age_threshold': 60,          # Wait for file to be stable (seconds)
        'sleep_interval': 10,              # Check interval (seconds)
        'max_retries': 10,                # Number of full upload attempts
        'chunk_size_mb': 1,               # Small chunks for unstable connections
        'upload_timeout': 7200,           # 2 hours total timeout
        'retry_max': 10,                  # Number of retries for transient errors
        'retry_delay': 5,                 # Initial delay between retries (seconds)
        'retry_max_delay': 30,            # Maximum delay between retries (seconds)
        'min_free_space_gb': 0,           # Minimum free space required
        'daily_report_enabled': True,      # Enable daily reporting
        'inactivity_threshold': 2,         # Hours of inactivity before alert
        'report_directory': './reports',
        'report_time': '23:59',
        'report_filename_format': 'upload_report_%Y%m%d.json',
        'report_upload_prefix': 'reports'
    }
    
    for key, value in defaults.items():
        if key not in uploader_config:
            uploader_config[key] = value
    
    # Verify credentials file if specified
    if 'credentials_file' in uploader_config:
        if not os.path.exists(uploader_config['credentials_file']):
            logging.warning(f'Credentials file {uploader_config["credentials_file"]} not found')
            del uploader_config['credentials_file']
        else:
            logging.info(f'Using credentials from {uploader_config["credentials_file"]}')
    
    # Start monitoring
    monitor_and_upload(uploader_config)


if __name__ == '__main__':
    main()
