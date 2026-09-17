import unittest
import json
from unittest.mock import patch, MagicMock
from veda.updater import production_updater, STATE_UP_TO_DATE, STATE_UPDATE_AVAILABLE

class TestUpdater(unittest.TestCase):
    def test_current_version_matches_system(self):
        from veda.version import VERSION
        self.assertEqual(production_updater.current_version, VERSION)

    @patch('urllib.request.urlopen')
    def test_update_available_flow(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_payload = {
            "version": "1.1.0",
            "build": 1100,
            "mandatory": False,
            "title": "V.E.D.A. 1.1.0",
            "release_date": "2026-09-17",
            "release_notes": ["OTA Engine", "Bug fixes"],
            "download_url": "https://example.com/VEDA-1.1.0.exe",
            "sha256": "fake_sha256"
        }
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = production_updater.check_for_updates()
        self.assertTrue(res["success"])
        self.assertTrue(res["update_available"])
        self.assertEqual(res["latest_version"], "1.1.0")
        self.assertEqual(production_updater.state, STATE_UPDATE_AVAILABLE)

    @patch('urllib.request.urlopen')
    def test_up_to_date_flow(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_payload = {
            "version": "1.0.0",
            "build": 1000
        }
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = production_updater.check_for_updates()
        self.assertTrue(res["success"])
        self.assertFalse(res["update_available"])
        self.assertEqual(production_updater.state, STATE_UP_TO_DATE)

if __name__ == '__main__':
    unittest.main()
