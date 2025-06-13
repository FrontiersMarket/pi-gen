#!/usr/bin/env python3
import unittest
from unittest.mock import patch, MagicMock, call
import os
import subprocess
import time
from rtsp_streamer import start_stream, monitor_stream

class TestRTSPStreamer(unittest.TestCase):
    def setUp(self):
        self.rtsp_url = "rtsp://example.com/stream"
        self.output_dir = "/tmp/test_output"
        self.segment_time = 60
        self.file_prefix = "test"
        self.config = {
            'socket_timeout': 5,
            'transport_protocol': 'tcp',
            'max_retry_interval': 60,
            'max_retries': 3
        }

    def tearDown(self):
        # Clean up any test directories
        if os.path.exists(self.output_dir):
            try:
                os.rmdir(self.output_dir)
            except OSError:
                pass

    @patch('subprocess.Popen')
    def test_start_stream_tcp(self, mock_popen):
        # Setup mock process
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        # Call the function
        process = start_stream(
            self.rtsp_url,
            self.output_dir,
            self.segment_time,
            self.file_prefix,
            self.config
        )

        # Verify the correct command was constructed
        expected_cmd = [
            'ffmpeg',
            '-rtsp_transport', 'tcp',
            '-stimeout', '5000000',
            '-rtsp_flags', 'prefer_tcp',
            '-i', self.rtsp_url,
            '-c', 'copy',
            '-f', 'segment',
            '-segment_time', '60',
            '-segment_atclocktime', '1',
            '-strftime', '1',
            '-copyts',
            '-start_at_zero',
            '-avoid_negative_ts', '1',
            os.path.join(self.output_dir, 'test_%Y%m%d_%H%M%S.ts')
        ]
        mock_popen.assert_called_once_with(
            expected_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

    @patch('subprocess.Popen')
    def test_start_stream_udp(self, mock_popen):
        # Test with UDP transport
        config = self.config.copy()
        config['transport_protocol'] = 'udp'
        
        process = start_stream(
            self.rtsp_url,
            self.output_dir,
            self.segment_time,
            self.file_prefix,
            config
        )

        # Verify UDP command doesn't include TCP-specific flags
        cmd = mock_popen.call_args[0][0]
        self.assertIn('-rtsp_transport', cmd)
        self.assertIn('udp', cmd)
        self.assertNotIn('prefer_tcp', cmd)

    @patch('os.makedirs')
    @patch('time.sleep')
    @patch('subprocess.Popen')
    def test_monitor_stream_retry_behavior(self, mock_popen, mock_sleep, mock_makedirs):
        # Setup mock process with failure then success
        mock_process1 = MagicMock()
        mock_process1.communicate.return_value = (b'', b'Error')
        mock_process1.returncode = 1

        mock_process2 = MagicMock()
        mock_process2.communicate.return_value = (b'', b'')
        mock_process2.returncode = 0

        mock_popen.side_effect = [mock_process1, mock_process2]

        # Set up config with limited retries
        config = self.config.copy()
        config['max_retries'] = 1

        # Monitor stream with 1 second sleep interval
        monitor_stream(
            self.rtsp_url,
            self.output_dir,
            self.segment_time,
            1,
            self.file_prefix,
            config
        )

        # Verify retry behavior
        self.assertEqual(mock_popen.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)
        mock_sleep.assert_called_with(1)  # First retry should use base interval

    @patch('os.makedirs')
    @patch('subprocess.Popen')
    def test_monitor_stream_directory_creation(self, mock_popen, mock_makedirs):
        # Setup mock process
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b'', b'')
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        # Call monitor_stream
        monitor_stream(
            self.rtsp_url,
            self.output_dir,
            self.segment_time,
            1,
            self.file_prefix,
            self.config
        )

        # Verify directory creation
        mock_makedirs.assert_called_once_with(self.output_dir, exist_ok=True)

if __name__ == '__main__':
    unittest.main()
