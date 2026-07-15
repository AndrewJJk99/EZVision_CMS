import * as React from 'react';
import { listCalibrations, detectLaser } from '../../../services/measurement.api';

export function useCmsWorkspace() {
  const [uiCamera, setUiCamera] = React.useState(1);
  const cameraIdBackend = uiCamera - 1;

  const [calibrations, setCalibrations] = React.useState([]);
  const [calibFile, setCalibFile] = React.useState('');

  const [resultImage, setResultImage] = React.useState(null); // 레이저 확대본
  const [resultImageFull, setResultImageFull] = React.useState(null); // 원본 전체
  const [resultCrop, setResultCrop] = React.useState(null); // {x0,y0,x1,y1}
  const [imgWidth, setImgWidth] = React.useState(4096);
  const [imgHeight, setImgHeight] = React.useState(3000);
  const [detectInfo, setDetectInfo] = React.useState(null);

  // 응답의 확대본/원본/crop을 한 번에 반영
  const applyImages = React.useCallback((res) => {
    if (!res) return;
    setResultImage(res.image ?? null);
    setResultImageFull(res.image_full ?? res.image ?? null);
    setResultCrop(res.crop ?? null);
  }, []);

  const [loading, setLoading] = React.useState(false);
  const [message, setMessage] = React.useState('');
  const [severity, setSeverity] = React.useState('info');

  // 레이저 색(파랑/빨강) — 페이지 간 유지되도록 localStorage에 저장.
  const [laserColor, setLaserColorState] = React.useState(() => {
    try {
      const v = window.localStorage.getItem('cms_laser_color');
      return v === 'red' || v === 'blue' ? v : 'blue';
    } catch (e) {
      return 'blue';
    }
  });
  const setLaserColor = React.useCallback((color) => {
    const c = color === 'red' ? 'red' : 'blue';
    setLaserColorState(c);
    try {
      window.localStorage.setItem('cms_laser_color', c);
    } catch (e) {
      /* ignore */
    }
  }, []);

  // 레이저 검출은 백엔드의 단일 강건 자동 검출기가 담당한다. 색만 전달.
  const detectionPayload = React.useCallback(() => ({ laser_color: laserColor }), [laserColor]);

  const refreshCalibrations = React.useCallback(async () => {
    try {
      const res = await listCalibrations();
      const items = res?.calibrations || [];
      setCalibrations(items);
      if (items.length && !calibFile) {
        const forCamera = items.find((c) => c.camera_id === cameraIdBackend);
        setCalibFile((forCamera || items[0]).file);
      }
    } catch (e) {
      setSeverity('warning');
      setMessage(e?.data?.error || e?.message || '캘리브레이션 목록 조회 실패');
    }
  }, [calibFile, cameraIdBackend]);

  React.useEffect(() => {
    refreshCalibrations();
  }, [refreshCalibrations]);

  const applySize = (res) => {
    const w = res?.image_size?.width;
    const h = res?.image_size?.height;
    if (w) setImgWidth(w);
    if (h) setImgHeight(h);
  };

  const run = async (fn, okMsg) => {
    setLoading(true);
    setMessage('');
    try {
      const res = await fn();
      setSeverity('success');
      setMessage(okMsg);
      return res;
    } catch (e) {
      setSeverity('error');
      setMessage(e?.data?.error || e?.message || '요청 실패');
      return null;
    } finally {
      setLoading(false);
    }
  };

  const handleCaptureDetect = async (okMsg = '캡처 & 검출 완료', extra = {}) => {
    const res = await run(
      () => detectLaser(cameraIdBackend, {
        calibration_file: calibFile || null,
        use_stored: false,
        ...detectionPayload(),
        ...extra,
      }),
      okMsg,
    );
    if (res) {
      applyImages(res);
      setDetectInfo(res);
      applySize(res);
    }
  };

  const handleRedetect = async (extra = {}) => {
    const res = await run(
      () => detectLaser(cameraIdBackend, {
        calibration_file: calibFile || null,
        use_stored: true,
        ...detectionPayload(),
        ...extra,
      }),
      '재검출 완료 (같은 이미지)',
    );
    if (res) {
      applyImages(res);
      setDetectInfo(res);
      applySize(res);
    }
  };

  const applyCaptureResult = (res) => {
    if (!res) return;
    applyImages(res);
    setDetectInfo(res);
    applySize(res);
  };

  return {
    uiCamera,
    setUiCamera,
    cameraIdBackend,
    calibrations,
    calibFile,
    setCalibFile,
    resultImage,
    setResultImage,
    resultImageFull,
    setResultImageFull,
    resultCrop,
    setResultCrop,
    applyImages,
    imgWidth,
    imgHeight,
    detectInfo,
    loading,
    message,
    severity,
    run,
    handleCaptureDetect,
    handleRedetect,
    detectionPayload,
    applyCaptureResult,
    refreshCalibrations,
    laserColor,
    setLaserColor,
  };
}
