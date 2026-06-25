import React from 'react';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import CameraControl3 from './CameraGrid/components/CameraControls/CameraControl3';
import { getCameraStatus } from '../../services/camera.api';

export default function SettingsGrid() {
  const [statusHint, setStatusHint] = React.useState('');

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getCameraStatus();
        const cameras = res?.status?.cameras || [];
        const cam1 = cameras.find((c) => (c.ui_camera_id ?? c.camera_id + 1) === 1);
        if (!cam1) return;
        if (!cam1.has_camera) {
          if (!cancelled) {
            setStatusHint(
              'Camera 1이 아직 매핑되지 않았습니다. 아래 Camera Mapping에서 디바이스를 연결한 뒤 저장하세요.'
            );
          }
          return;
        }
        if (!cam1.is_open) {
          if (!cancelled) {
            setStatusHint(
              'Camera 1에 IP는 저장됐지만 카메라가 열려 있지 않습니다. MVS 등 다른 프로그램을 종료하고 Camera Mapping 저장 후 재시작하세요.'
            );
          }
        }
      } catch (_err) {
        if (!cancelled) {
          setStatusHint('Camera API(7070)에 연결할 수 없습니다. camera 서버가 실행 중인지 확인하세요.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Box sx={{ width: '100%', maxWidth: '100%', alignSelf: 'stretch' }}>
      <Stack spacing={1} sx={{ width: '100%' }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          Camera Settings
        </Typography>
        {statusHint ? (
          <Alert severity="warning" sx={{ mb: 1 }}>
            {statusHint}
          </Alert>
        ) : null}
        <Box sx={{ width: '100%', overflowX: 'auto' }}>
          <CameraControl3 />
        </Box>
      </Stack>
    </Box>
  );
}
