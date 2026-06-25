import { API } from '../config/api';
import { request } from '../lib/httpClient';

const MEASUREMENT_API = `${API.camera}/measurement`;

export const listCalibrations = () => request(`${MEASUREMENT_API}/calibrations`);

export const analyzeMeasurement = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/analyze/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 60000,
  });

// 캡처: 같은 이미지를 튜닝/LUT에서 재사용
export const captureFrame = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/capture/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 60000,
  });

// 단계 A: 레이저 선 검출(튜닝) → 점 목록 반환
export const detectLaser = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/laser/detect/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 60000,
  });

// 단계 B: 계단블록으로 LUT 생성/저장
export const buildLut = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/lut/build/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 60000,
  });

export const getLut = (cameraIdBackend) =>
  request(`${MEASUREMENT_API}/lut/${cameraIdBackend}`);

// 단계 C: 두 구간 단차 측정
export const measureStep = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/measure/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 60000,
  });

// 단계 C-2: 자동 단 분석 (계단 전체)
export const measureSteps = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/measure/steps/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 60000,
  });
