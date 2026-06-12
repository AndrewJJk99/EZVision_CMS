import { useMemo } from 'react';

export const useCameraLayout = (activeCameras, activeCameraCount, firstActiveCamera) => {
  // 각 카메라의 그리드 크기 계산
  const cameraGridSizes = useMemo(() => {
    const sizes = {};
    
    // 활성화된 카메라가 없을 때
    if (activeCameraCount === 0) {
      return sizes;
    }

    // 활성화된 카메라가 1개일 때
    if (activeCameraCount === 1) {
      Object.keys(activeCameras).forEach(cameraId => {
        if (activeCameras[cameraId]) {
          sizes[cameraId] = { xs: 8, md: 12 };
        }
      });
      return sizes;
    }

    // 활성화된 카메라가 2개일 때
    if (activeCameraCount === 2) {
      Object.keys(activeCameras).forEach(cameraId => {
        if (activeCameras[cameraId]) {
          sizes[cameraId] = { xs: 8, md: 6 };
        }
      });
      return sizes;
    }

    // 활성화된 카메라가 3개일 때
    if (activeCameraCount === 3) {
      Object.keys(activeCameras).forEach(cameraId => {
        if (activeCameras[cameraId]) {
          // 첫 번째 활성화된 카메라는 전체 너비, 나머지는 절반
          if (cameraId === firstActiveCamera) {
            sizes[cameraId] = { xs: 8, md: 12 };
          } else {
            sizes[cameraId] = { xs: 8, md: 6 };
          }
        }
      });
      return sizes;
    }

    // 활성화된 카메라가 4개일 때
    if (activeCameraCount === 4) {
      Object.keys(activeCameras).forEach(cameraId => {
        if (activeCameras[cameraId]) {
          sizes[cameraId] = { xs: 8, md: 6 };
        }
      });
      return sizes;
    }

    return sizes;
  }, [activeCameras, activeCameraCount, firstActiveCamera]);

  // 레이아웃 타입 반환 (디버깅 및 스타일링용)
  const layoutType = useMemo(() => {
    if (activeCameraCount === 0) return 'empty';
    if (activeCameraCount === 1) return 'single';
    if (activeCameraCount === 2) return 'dual';
    if (activeCameraCount === 3) return 'triple';
    if (activeCameraCount === 4) return 'quad';
    return 'unknown';
  }, [activeCameraCount]);

  return {
    cameraGridSizes,
    layoutType
  };
};
