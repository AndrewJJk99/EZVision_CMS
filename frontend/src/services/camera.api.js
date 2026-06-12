import { API } from '../config/api';
import { request } from '../lib/httpClient';

const UI_CAMERA_API = `${API.ui}/camera`;
const CAMERA_API = `${API.camera}/camera`;
const CAMERA_WS_BASE = API.camera.replace(/^http/, 'ws');

export const getFeatureList = () => request(`${UI_CAMERA_API}/get_feature`);

export const saveFeature = (payload) =>
  request(`${UI_CAMERA_API}/save_feature`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

/** CMS 1단계: 촬영(shutter) 없음 — 매핑 변경 항상 허용 */
export const getLatestShutter = async () => [{ STATUS: 'E' }];

export const getCameraStatus = (cameraId) => {
  const query = typeof cameraId === 'number' ? `?camera_id=${cameraId}` : '';
  return request(`${CAMERA_API}/status${query}`);
};

export const getCameraFeature = (cameraId) =>
  request(`${CAMERA_API}/get_feature/${cameraId}`, {
    method: 'POST',
  });

export const getCameraDevices = () => request(`${CAMERA_API}/devices`);

export const restartCamera = () =>
  request(`${CAMERA_API}/restart`, {
    method: 'POST',
  });

export const setCameraFeature = (cameraId, payload) =>
  request(`${CAMERA_API}/set_feature/${cameraId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const getCameraWsUrl = (cameraId) => `${CAMERA_WS_BASE}/camera/ws/${cameraId}`;

const CALIBRATION_API = `${API.camera}/calibration`;

export const getCalibrationStatus = (cameraIdBackend) =>
  request(`${CALIBRATION_API}/status/${cameraIdBackend}`);

export const startCalibration = (cameraIdBackend, config) =>
  request(`${CALIBRATION_API}/start/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(config || {}),
  });

export const stopCalibration = (cameraIdBackend) =>
  request(`${CALIBRATION_API}/stop/${cameraIdBackend}`, { method: 'POST' });

export const captureCalibrationSample = (cameraIdBackend) =>
  request(`${CALIBRATION_API}/capture/${cameraIdBackend}`, {
    method: 'POST',
    timeout: 60000,
  });

export const runCalibration = (cameraIdBackend) =>
  request(`${CALIBRATION_API}/run/${cameraIdBackend}`, {
    method: 'POST',
    timeout: 60000,
  });

export const saveCalibration = (cameraIdBackend) =>
  request(`${CALIBRATION_API}/save/${cameraIdBackend}`, { method: 'POST' });

export const resetCalibrationSamples = (cameraIdBackend) =>
  request(`${CALIBRATION_API}/reset/${cameraIdBackend}`, { method: 'POST' });

export const getCalibrationPreviewUrl = (cameraIdBackend) =>
  `${CALIBRATION_API}/preview/${cameraIdBackend}?t=${Date.now()}`;
