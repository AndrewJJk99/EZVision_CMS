import { API } from '../config/api';
import { request } from '../lib/httpClient';

const UI_CAMERA_API = `${API.ui}/camera`;
const CAMERA_API = `${API.camera}/camera`;
const CAMERA_WS_BASE = API.camera.replace(/^http/, 'ws');

export const getFeatureList = () =>
  request(`${UI_CAMERA_API}/get_feature`).then((data) => (Array.isArray(data) ? data : []));

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

/**
 * 실제 연결/매핑된 카메라 목록을 백엔드 상태에서 동적으로 조회.
 * 반환: [{ backend, ui, ip, connected }] — 연결(has_camera) 또는 매핑(db_ip)된 슬롯만.
 * 카메라가 추가/매핑되면 재조회 시 자동으로 목록에 나타난다.
 */
export const getAvailableCameras = async () => {
  const res = await getCameraStatus();
  const list = res?.status?.cameras;
  if (!Array.isArray(list)) return [];
  return list
    .filter((c) => c && (c.has_camera || c.db_ip))
    .map((c) => ({
      backend: c.camera_id,
      ui: c.ui_camera_id ?? c.camera_id + 1,
      ip: c.device_ip || c.db_ip || null,
      connected: !!c.has_camera,
    }));
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

export const startCamera = () =>
  request(`${CAMERA_API}/start`, {
    method: 'POST',
  });

export const setCameraFeature = (cameraId, payload) =>
  request(`${CAMERA_API}/set_feature/${cameraId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const getCameraWsUrl = (cameraId) => `${CAMERA_WS_BASE}/camera/ws/${cameraId}`;
