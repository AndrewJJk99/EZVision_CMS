import { API } from '../config/api';
import { request } from '../lib/httpClient';

const MEASUREMENT_API = `${API.camera}/measurement`;

export const listCalibrations = () => request(`${MEASUREMENT_API}/calibrations`);

export const listLuts = () => request(`${MEASUREMENT_API}/luts`);

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
    timeout: 120000,
  });

// 단계 A: 레이저 선 검출(튜닝) → 점 목록 반환
export const detectLaser = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/laser/detect/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 120000,
  });

// 저장된 LUT 생성 이미지로 레이저 재검출 (카메라 캡처 없음)
export const detectLutImage = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/lut/image/detect/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 120000,
  });

// 단계 B: 계단블록으로 LUT 생성 (기본: 미리보기만, save:true면 즉시 저장)
export const buildLut = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/lut/build/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 120000,
  });

// 미리보기된 LUT draft 저장
export const saveLut = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/lut/save/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 60000,
  });

export const getLut = (cameraIdBackend, lutFile) => {
  const qs = lutFile ? `?lut_file=${encodeURIComponent(lutFile)}` : '';
  return request(`${MEASUREMENT_API}/lut/${cameraIdBackend}${qs}`);
};

export const deleteLut = (cameraIdBackend, lutFile) =>
  request(`${MEASUREMENT_API}/lut/${cameraIdBackend}?lut_file=${encodeURIComponent(lutFile)}`, {
    method: 'DELETE',
    timeout: 30000,
  });

// 단계 C: 두 구간 단차 측정
export const measureStep = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/measure/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 120000,
  });

// 단계 C-2: 자동 단 분석 (계단 전체)
export const measureSteps = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/measure/steps/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 120000,
  });

// 단계 D: 간격 측정 (레이저 직선 끝점)
export const measureGap = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/measure/gap/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 120000,
  });

// 간격용 mm/px: 체커보드 한 칸으로 계산·저장
export const getGapScale = (cameraIdBackend) =>
  request(`${MEASUREMENT_API}/gap/scale/${cameraIdBackend}`);

export const computeGapScale = (cameraIdBackend, payload) =>
  request(`${MEASUREMENT_API}/gap/scale/${cameraIdBackend}`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    timeout: 120000,
  });
