import * as React from 'react';
import { listCalibrations, detectLaser } from '../../../services/measurement.api';

export function useCmsWorkspace() {
  const [uiCamera, setUiCamera] = React.useState(1);
  const cameraIdBackend = uiCamera - 1;

  const [calibrations, setCalibrations] = React.useState([]);
  const [calibFile, setCalibFile] = React.useState('');

  const [method, setMethod] = React.useState('auto');
  const [blueBoost, setBlueBoost] = React.useState(true);
  const [threshOffset, setThreshOffset] = React.useState(0);
  const [hLow, setHLow] = React.useState(90);
  const [hHigh, setHHigh] = React.useState(130);
  const [sMin, setSMin] = React.useState(80);
  const [vMin, setVMin] = React.useState(80);
  const [bridgeGap, setBridgeGap] = React.useState(25);
  const [roiEnabled, setRoiEnabled] = React.useState(false);
  const [roiY, setRoiY] = React.useState([0, 720]);

  const [resultImage, setResultImage] = React.useState(null);
  const [imgWidth, setImgWidth] = React.useState(1280);
  const [imgHeight, setImgHeight] = React.useState(720);
  const [detectInfo, setDetectInfo] = React.useState(null);

  const [loading, setLoading] = React.useState(false);
  const [message, setMessage] = React.useState('');
  const [severity, setSeverity] = React.useState('info');

  const detectionPayload = React.useCallback(
    () => ({
      method,
      blue_boost: blueBoost,
      thresh_offset: threshOffset,
      h_low: hLow,
      h_high: hHigh,
      s_min: sMin,
      v_min: vMin,
      keep_largest: true,
      bridge_gap: bridgeGap,
      roi_y0: roiEnabled ? roiY[0] : null,
      roi_y1: roiEnabled ? roiY[1] : null,
    }),
    [method, blueBoost, threshOffset, hLow, hHigh, sMin, vMin, bridgeGap, roiEnabled, roiY],
  );

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
    if (h) {
      setImgHeight(h);
      if (!roiEnabled) setRoiY([0, h]);
    }
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

  const handleCaptureDetect = async (okMsg = '캡처 & 검출 완료 (가장 긴 선만 자동 추출)') => {
    const res = await run(
      () => detectLaser(cameraIdBackend, { calibration_file: calibFile || null, use_stored: false, ...detectionPayload() }),
      okMsg,
    );
    if (res) {
      setResultImage(res.image);
      setDetectInfo(res);
      applySize(res);
    }
  };

  const handleRedetect = async () => {
    const res = await run(
      () => detectLaser(cameraIdBackend, { calibration_file: calibFile || null, use_stored: true, ...detectionPayload() }),
      '재검출 완료 (같은 이미지)',
    );
    if (res) {
      setResultImage(res.image);
      setDetectInfo(res);
      applySize(res);
    }
  };

  const applyCaptureResult = (res) => {
    if (!res) return;
    setResultImage(res.image);
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
    method,
    setMethod,
    blueBoost,
    setBlueBoost,
    threshOffset,
    setThreshOffset,
    hLow,
    setHLow,
    hHigh,
    setHHigh,
    sMin,
    setSMin,
    vMin,
    setVMin,
    bridgeGap,
    setBridgeGap,
    roiEnabled,
    setRoiEnabled,
    roiY,
    setRoiY,
    resultImage,
    setResultImage,
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
  };
}
