#!/usr/bin/env python3
import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import base64
import hashlib
from pathlib import Path
from uploader import compute_md5_base64, upload_file, get_free_space_gb, ensure_directory_space

class TestUploader(unittest.TestCase):
    def setUp(self):
        self.test_file_path = "/tmp/test_file.mp4"
        self.test_content = b"test content"
        self.test_md5 = base64.b64encode(hashlib.md5(self.test_content).digest()).decode('utf-8')
        self.bucket = MagicMock()
        self.blob = MagicMock()
        self.bucket.blob.return_value = self.blob
        self.config = {
            'chunk_size': 8 * 1024 * 1024,  # 8MB
            'max_retries': 3
        }

    def test_compute_md5_base64(self):
        # Test MD5 computation
        with patch("builtins.open", mock_open(read_data=self.test_content)):
            md5_hash = compute_md5_base64(self.test_file_path)
            self.assertEqual(md5_hash, self.test_md5)

    @patch('logging.info')
    @patch('logging.error')
    def test_upload_file_success(self, mock_error, mock_info):
        # Setup mock blob
        self.blob.md5_hash = self.test_md5

        # Mock the local MD5 computation
        with patch('uploader.compute_md5_base64') as mock_md5:
            mock_md5.return_value = self.test_md5
            
            success, md5_hash, error = upload_file(
                self.bucket,
                self.test_file_path,
                "destination/test_file.mp4",
                self.config
            )

        # Verify success
        self.assertTrue(success)
        self.assertEqual(md5_hash, self.test_md5)
        self.assertIsNone(error)
        
        # Verify blob operations
        self.blob.upload_from_filename.assert_called_once_with(
            self.test_file_path,
            timeout=120
        )
        self.blob.reload.assert_called_once()
        self.blob.delete.assert_not_called()

    @patch('logging.info')
    @patch('logging.error')
    def test_upload_file_checksum_mismatch(self, mock_error, mock_info):
        # Setup mock blob with wrong MD5
        self.blob.md5_hash = "wrong_md5"

        # Mock the local MD5 computation
        with patch('uploader.compute_md5_base64') as mock_md5:
            mock_md5.return_value = self.test_md5
            
            success, md5_hash, error = upload_file(
                self.bucket,
                self.test_file_path,
                "destination/test_file.mp4",
                self.config
            )

        # Verify failure
        self.assertFalse(success)
        self.assertIsNone(md5_hash)
        self.assertIn("Checksum mismatch", error)
        
        # Verify corrupted upload was deleted
        self.blob.delete.assert_called()

    @patch('shutil.disk_usage')
    def test_get_free_space_gb(self, mock_disk_usage):
        # Mock disk_usage to return 10GB free space
        mock_stats = MagicMock()
        mock_stats.free = 10 * 1024 * 1024 * 1024  # 10GB in bytes
        mock_disk_usage.return_value = mock_stats

        free_space = get_free_space_gb("/test/dir")
        self.assertEqual(free_space, 10)

    @patch('pathlib.Path.mkdir')
    @patch('shutil.disk_usage')
    def test_ensure_directory_space_primary_sufficient(self, mock_disk_usage, mock_mkdir):
        # Mock disk_usage to return 20GB free space
        mock_stats = MagicMock()
        mock_stats.free = 20 * 1024 * 1024 * 1024  # 20GB in bytes
        mock_disk_usage.return_value = mock_stats

        primary_dir = "/primary"
        backup_dir = "/backup"
        min_free_space_gb = 10

        result = ensure_directory_space(primary_dir, backup_dir, min_free_space_gb)
        self.assertEqual(result, primary_dir)
        mock_mkdir.assert_not_called()

    @patch('pathlib.Path.mkdir')
    @patch('pathlib.Path.write_text')
    @patch('pathlib.Path.unlink')
    @patch('shutil.disk_usage')
    def test_ensure_directory_space_switch_to_backup(self, mock_disk_usage, mock_unlink, 
                                                   mock_write, mock_mkdir):
        # Mock disk_usage to return different values for primary and backup
        def mock_disk_usage_fn(path):
            mock_stats = MagicMock()
            if path == "/primary":
                mock_stats.free = 5 * 1024 * 1024 * 1024  # 5GB
            else:
                mock_stats.free = 50 * 1024 * 1024 * 1024  # 50GB
            return mock_stats

        mock_disk_usage.side_effect = mock_disk_usage_fn

        primary_dir = "/primary"
        backup_dir = "/backup"
        min_free_space_gb = 10

        result = ensure_directory_space(primary_dir, backup_dir, min_free_space_gb)
        self.assertEqual(result, backup_dir)
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_ensure_directory_space_no_backup_configured(self):
        primary_dir = "/primary"
        backup_dir = ""  # Empty backup dir
        min_free_space_gb = 10

        result = ensure_directory_space(primary_dir, backup_dir, min_free_space_gb)
        self.assertEqual(result, primary_dir)

if __name__ == '__main__':
    unittest.main()
