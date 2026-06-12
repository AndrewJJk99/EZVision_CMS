import { useState, useCallback } from 'react';

export const useCameraState = () => {
  const [activeCameras, setActiveCameras] = useState({
    1: false,
    2: false,
    3: false,
    4: false
  });

  // 카메라 상태 변경 핸들러
  const handleCameraStateChange = useCallback((cameraStates) => {
    setActiveCameras({
      1: cameraStates[1]?.enabled || false,
      2: cameraStates[2]?.enabled || false,
      3: cameraStates[3]?.enabled || false,
      4: cameraStates[4]?.enabled || false
    });
  }, []);

  // 개별 카메라 상태 토글
  const toggleCamera = useCallback((cameraId) => {
    setActiveCameras(prev => ({
      ...prev,
      [cameraId]: !prev[cameraId]
    }));
  }, []);

  // 모든 카메라 비활성화
  const disableAllCameras = useCallback(() => {
    setActiveCameras({
      1: false,
      2: false,
      3: false,
      4: false
    });
  }, []);

  // 활성화된 카메라 수 계산
  const activeCameraCount = Object.values(activeCameras).filter(Boolean).length;

  // 첫 번째 활성화된 카메라 번호 찾기
  const firstActiveCamera = Object.entries(activeCameras).find(([_, isActive]) => isActive)?.[0];

  return {
    activeCameras,
    activeCameraCount,
    firstActiveCamera,
    handleCameraStateChange,
    toggleCamera,
    disableAllCameras
  };
};
