import { useCallback, useEffect, useRef } from 'react';
import { getCalibrationPreviewUrl } from '../../../../services/camera.api';

/**
 * 캘리브레이션 모드: WebSocket 스트림 위에 체커보드 오버레이 프리뷰를 주기적으로 그립니다.
 * (WebSocket은 유지 — 프리뷰 실패 시 일반 스트림이 보임)
 */
export function useCalibrationPreview({
  enabled,
  cameraIdBackend,
  canvasRef,
  containerRef,
  activeCameraCountRef,
  parentHeightRef,
}) {
  const intervalRef = useRef(null);
  const inFlightRef = useRef(false);

  const drawBlob = useCallback(
    (blob) => {
      const canvas = canvasRef.current;
      if (!canvas || !blob) return;

      const imageUrl = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => {
        const ctx = canvas.getContext('2d');
        const aspectRatio = img.height / img.width;
        const windowWidth = window.innerWidth;
        const currentCameraCount = activeCameraCountRef.current || 1;

        let widthRatio = 1.0;
        let maxWidth = windowWidth;
        if (currentCameraCount === 1) {
          widthRatio = 0.75;
          maxWidth = 1200;
        } else if (currentCameraCount >= 3) {
          widthRatio = 0.92;
          maxWidth = 1200;
        }

        const availableWidth = windowWidth * widthRatio;
        const calculatedWidth = Math.floor(availableWidth / currentCameraCount);
        let currentDisplayWidth = Math.max(300, Math.min(maxWidth, calculatedWidth));
        let calculatedHeight = currentDisplayWidth * aspectRatio;

        const parentBox = containerRef.current || canvas.parentElement;
        if (parentBox) {
          const parentHeight = parentBox.clientHeight || parentHeightRef.current;
          if (parentHeight) {
            const heightBasedWidth = Math.floor(parentHeight / aspectRatio);
            if (heightBasedWidth < currentDisplayWidth) {
              currentDisplayWidth = heightBasedWidth;
              calculatedHeight = currentDisplayWidth * aspectRatio;
            } else if (calculatedHeight > parentHeight) {
              currentDisplayWidth = Math.floor(parentHeight / aspectRatio);
              calculatedHeight = currentDisplayWidth * aspectRatio;
            }
            parentHeightRef.current = parentHeight;
          }
        }

        // 크기가 바뀔 때만 canvas 치수를 재설정 (매 프레임 재설정 시 캔버스가
        // 지워졌다 그려지며 번쩍거림 → 변경 없을 땐 불투명 JPEG로 덮어쓰기만)
        const targetW = Math.round(currentDisplayWidth);
        const targetH = Math.round(calculatedHeight);
        if (canvas.width !== targetW || canvas.height !== targetH) {
          canvas.width = targetW;
          canvas.height = targetH;
        }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(imageUrl);
      };
      img.onerror = () => URL.revokeObjectURL(imageUrl);
      img.src = imageUrl;
    },
    [activeCameraCountRef, canvasRef, containerRef, parentHeightRef],
  );

  useEffect(() => {
    if (!enabled) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return undefined;
    }

    const tick = async () => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      try {
        const res = await fetch(getCalibrationPreviewUrl(cameraIdBackend), { cache: 'no-store' });
        if (!res.ok) return;
        const blob = await res.blob();
        drawBlob(blob);
      } catch {
        // 이전 프레임 유지
      } finally {
        inFlightRef.current = false;
      }
    };

    tick();
    intervalRef.current = setInterval(tick, 200);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [enabled, cameraIdBackend, drawBlob]);
}
