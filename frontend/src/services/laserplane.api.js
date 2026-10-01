import { API } from '../config/api';
import { request } from '../lib/httpClient';

const LP_API = `${API.cms}/laserplane`;

export const lpGetModel = (cam, planeFile) =>
  request(`${LP_API}/model/${cam}${planeFile ? `?plane_file=${encodeURIComponent(planeFile)}` : ''}`);

export const lpMeasure = (cam, payload) =>
  request(`${LP_API}/measure/${cam}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 30000,
  });

export const lpMeasureCapture = (cam, payload) =>
  request(`${LP_API}/measure_capture/${cam}`, {
    method: 'POST', body: JSON.stringify(payload || {}), timeout: 120000,
  });

// 라이브(연속) 측정 — 짧은 주기로 호출. 색 고정 + 밴드 추적으로 빠르게.
export const lpMeasureLive = (cam, payload) =>
  request(`${LP_API}/measure_live/${cam}`, {
    method: 'POST', body: JSON.stringify(payload || {}), timeout: 15000,
  });

export const lpMeasureFile = (cam, file, laserColor, detector, planeFile, sensitivity) => {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('laser_color', laserColor || 'auto');
  fd.append('detector', detector || 'chroma');
  if (planeFile) fd.append('plane_file', planeFile);
  if (sensitivity != null) fd.append('sensitivity', String(sensitivity));
  return request(`${LP_API}/measure_file/${cam}`, { method: 'POST', body: fd, timeout: 120000 });
};

// ── 통합 캘리브레이션 (내부파라미터 + 광평면 한 번에) ──
export const lpcStatus = (cam) => request(`${LP_API}/combined/status/${cam}`);

export const lpcStart = (cam, payload) =>
  request(`${LP_API}/combined/start/${cam}`, {
    method: 'POST', body: JSON.stringify(payload || {}), timeout: 30000,
  });

export const lpcCaptureOff = (cam) =>
  request(`${LP_API}/combined/capture_off/${cam}`, { method: 'POST', body: '{}', timeout: 120000 });

export const lpcCaptureOn = (cam, payload) =>
  request(`${LP_API}/combined/capture_on/${cam}`, {
    method: 'POST', body: JSON.stringify(payload || {}), timeout: 120000,
  });

export const lpcCaptureSingle = (cam, payload) =>
  request(`${LP_API}/combined/capture_single/${cam}`, {
    method: 'POST', body: JSON.stringify(payload || {}), timeout: 120000,
  });

export const lpcFit = (cam) =>
  request(`${LP_API}/combined/fit/${cam}`, { method: 'POST', body: '{}', timeout: 60000 });

export const lpcSave = (cam, name) =>
  request(`${LP_API}/combined/save/${cam}`, { method: 'POST', body: JSON.stringify({ name: name || null }) });

export const lpListPlanes = (cam) => request(`${LP_API}/planes/${cam}`);

export const lpcReset = (cam) =>
  request(`${LP_API}/combined/reset/${cam}`, { method: 'POST', body: '{}' });

// ── 카메라 단독 캘리브레이션 (레이저 없이 내부파라미터만) — 내부 RMS 진단 ──
export const lpCamCalStart = (cam, payload) =>
  request(`${LP_API}/camcalib/start/${cam}`, { method: 'POST', body: JSON.stringify(payload || {}), timeout: 30000 });

export const lpCamCalCapture = (cam) =>
  request(`${LP_API}/camcalib/capture/${cam}`, { method: 'POST', body: '{}', timeout: 120000 });

export const lpCamCalFit = (cam) =>
  request(`${LP_API}/camcalib/fit/${cam}`, { method: 'POST', body: '{}', timeout: 60000 });

export const lpCamCalReset = (cam) =>
  request(`${LP_API}/camcalib/reset/${cam}`, { method: 'POST', body: '{}' });
