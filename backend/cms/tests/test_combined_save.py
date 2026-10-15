import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routers import laserplane
from utils import laser_plane_manager as lpm


class CombinedSaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.plane_dir = Path(self.temp.name) / 'laserplane_data'
        self.session_dir = Path(self.temp.name) / 'session_data'
        for name, value in [('PLANE_DIR', str(self.plane_dir)),
                            ('SESSION_DIR', str(self.session_dir)), ('_COMBINED', {})]:
            patcher = patch.object(laserplane, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(laserplane.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.session = lpm.LaserPlaneCombinedSession(0, 2, 2, 20, (640, 480))
        laserplane._COMBINED[0] = self.session

    def save(self):
        response = self.client.post('/laserplane/combined/save/0', json={'name': '테스트'})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        directory = self.plane_dir if result['has_model'] else self.session_dir
        path = directory / result['path']
        return result, json.loads(path.read_text(encoding='utf-8')), path

    def test_empty_session_can_be_saved(self):
        result, payload, _ = self.save()
        self.assertFalse(result['has_model'])
        self.assertEqual(payload['type'], 'laser_plane_combined_session')
        self.assertEqual(payload['session']['poses'], [])
        self.assertEqual(payload['meta']['name'], '테스트')
        self.assertEqual(self.client.get('/laserplane/planes/0').json()['planes'], [])

    def test_failed_fit_preserves_captures_and_pending_off(self):
        corners = np.array([[1, 1], [21, 1], [1, 21], [21, 21]], dtype=float)
        laser = np.column_stack((np.arange(8), np.ones(8)))
        self.session.add_off(corners)
        self.session.add_on(laser)
        self.session.add_off(corners + 2)
        response = self.client.post('/laserplane/combined/fit/0')
        self.assertEqual(response.status_code, 422)
        result, payload, _ = self.save()
        self.assertFalse(result['has_model'])
        self.assertEqual(payload['session']['poses'][0]['corners'], corners.tolist())
        self.assertEqual(payload['session']['poses'][0]['laser_uv'], laser.tolist())
        self.assertEqual(payload['session']['pending_corners'], (corners + 2).tolist())
        self.assertEqual(self.client.get('/laserplane/planes/0').json()['planes'], [])

    def test_quality_failure_can_save_and_reload_computed_model(self):
        corners = np.zeros((4, 2))
        laser = np.zeros((20, 2))
        self.session.poses = [lpm.CombinedPose(corners.copy(), laser.copy()) for _ in range(4)]
        line = np.column_stack((np.arange(20), np.zeros(20), np.full(20, 500)))
        calibration = (12.5, np.eye(3), np.zeros(5),
                       [np.zeros(3)] * 4, [np.array([0, 0, 500])] * 4)
        with patch.object(lpm.cv2, 'calibrateCamera', return_value=calibration), \
             patch.object(lpm, 'filter_points_in_quad', return_value=laser), \
             patch.object(lpm, 'board_points_to_3d', return_value=line):
            response = self.client.post('/laserplane/combined/fit/0')
        self.assertEqual(response.status_code, 200, response.text)
        fit = response.json()
        self.assertTrue(fit['degenerate'])
        self.assertTrue(fit['warning'])
        self.assertTrue(fit['status']['fitted'])
        result, payload, path = self.save()
        self.assertTrue(result['has_model'])
        self.assertTrue(payload['meta']['plane_health']['degenerate'])
        self.assertEqual(payload['meta']['intrinsic_rms_px'], 12.5)
        self.assertEqual(len(payload['session']['poses']), 4)
        loaded = lpm.LaserPlaneModel.load(str(path))
        np.testing.assert_allclose(loaded.n, self.session.model.n)
        np.testing.assert_allclose(loaded.K, self.session.K)
        planes = self.client.get('/laserplane/planes/0').json()['planes']
        self.assertEqual(planes[0]['file'], result['path'])

    def test_no_session_still_returns_clear_error(self):
        laserplane._COMBINED.clear()
        response = self.client.post('/laserplane/combined/save/0', json={})
        self.assertEqual(response.status_code, 409)


if __name__ == '__main__':
    unittest.main()
