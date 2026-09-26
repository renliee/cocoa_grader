"""Report links must use an address another device can open."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reports


class ReportOriginTests(unittest.TestCase):
    def test_explicit_origin_wins(self):
        with patch.dict(os.environ, {'KAKAO_PUBLIC_BASE_URL': 'https://qc.example.test'}, clear=False):
            self.assertEqual(reports._base_url('http://192.168.1.5:8080'), 'https://qc.example.test')

    def test_request_lan_origin_wins(self):
        with patch.dict(os.environ, {'KAKAO_PUBLIC_BASE_URL': ''}, clear=False):
            self.assertEqual(reports._base_url('http://192.168.1.5:8080'), 'http://192.168.1.5:8080')

    def test_local_preview_uses_lan_interface(self):
        with patch.dict(os.environ, {'KAKAO_PUBLIC_BASE_URL': ''}, clear=False), \
                patch.object(reports.os.path, 'exists', return_value=False), \
                patch.object(reports, '_lan_address', return_value='192.168.1.8'):
            self.assertEqual(reports._base_url('http://127.0.0.1:8081'), 'http://192.168.1.8:8081')

    def test_unavailable_lan_does_not_advertise_container_address(self):
        with patch.dict(os.environ, {'KAKAO_PUBLIC_BASE_URL': ''}, clear=False), \
                patch.object(reports.os.path, 'exists', return_value=True):
            self.assertEqual(reports._base_url('http://127.0.0.1:8080'), 'http://127.0.0.1:8080')


if __name__ == '__main__':
    unittest.main()
