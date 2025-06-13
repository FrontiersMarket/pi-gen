#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime, time
from pathlib import Path

class UploaderReport:
    def __init__(self, config):
        """Initialize report manager with configuration."""
        self.config = config
        self.report_data = {
            'start_time': datetime.now().isoformat(),
            'uploads': [],
            'failed_uploads': [],
            'stats': {
                'total_uploads': 0,
                'successful_uploads': 0,
                'failed_uploads': 0,
                'total_bytes_uploaded': 0
            }
        }
        self.last_activity = datetime.now()
        
        # Create report directory
        if self.config.get('daily_report_enabled'):
            os.makedirs(self.config['report_directory'], exist_ok=True)
    
    def record_upload(self, file_path, destination_blob_name, success, size_bytes, error=None):
        """Record an upload attempt."""
        self.last_activity = datetime.now()
        
        upload_record = {
            'timestamp': datetime.now().isoformat(),
            'file_path': file_path,
            'destination': destination_blob_name,
            'size_bytes': size_bytes,
            'success': success
        }
        
        if error:
            upload_record['error'] = str(error)
        
        if success:
            self.report_data['uploads'].append(upload_record)
            self.report_data['stats']['successful_uploads'] += 1
            self.report_data['stats']['total_bytes_uploaded'] += size_bytes
        else:
            self.report_data['failed_uploads'].append(upload_record)
            self.report_data['stats']['failed_uploads'] += 1
        
        self.report_data['stats']['total_uploads'] += 1
    
    def should_generate_report(self):
        """Check if it's time to generate a report based on time or inactivity."""
        if not self.config.get('daily_report_enabled'):
            return False
            
        now = datetime.now()
        
        # Check scheduled report time
        report_time_parts = self.config['report_time'].split(':')
        report_time = time(int(report_time_parts[0]), int(report_time_parts[1]))
        current_time = now.time()
        
        # Check inactivity threshold
        inactivity_hours = (now - self.last_activity).total_seconds() / 3600
        
        return (current_time >= report_time or 
                inactivity_hours >= self.config['inactivity_threshold'])
    
    def generate_report(self):
        """Generate a report file and return its path."""
        if not self.config.get('daily_report_enabled'):
            return None
            
        # Add end time to report
        self.report_data['end_time'] = datetime.now().isoformat()
        
        # Generate filename using configured format
        filename = datetime.now().strftime(self.config['report_filename_format'])
        report_path = os.path.join(self.config['report_directory'], filename)
        
        # Write report to file
        with open(report_path, 'w') as f:
            json.dump(self.report_data, f, indent=2)
        
        # Reset report data
        self.report_data = {
            'start_time': datetime.now().isoformat(),
            'uploads': [],
            'failed_uploads': [],
            'stats': {
                'total_uploads': 0,
                'successful_uploads': 0,
                'failed_uploads': 0,
                'total_bytes_uploaded': 0
            }
        }
        
        return report_path
