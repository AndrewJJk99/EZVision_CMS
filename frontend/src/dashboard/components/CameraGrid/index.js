import React from 'react';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Grid from '@mui/material/Grid2';

// Custom hooks
import { useCameraState } from './hooks/useCameraState';
import { useCameraLayout } from './hooks/useCameraLayout';

// Components
import CameraLayout from './components/CameraLayout';
import CameraControlPanel from './components/CameraControlPanel';

export default function CameraGrid() {
  // 카메라 상태 관리
  const {
    activeCameras,
    activeCameraCount,
    firstActiveCamera,
    handleCameraStateChange
  } = useCameraState();

  // 카메라 레이아웃 계산
  const { cameraGridSizes, layoutType } = useCameraLayout(
    activeCameras, 
    activeCameraCount, 
    firstActiveCamera
  );

  return (
    <Box sx={{ width: '100%', maxWidth: { sm: '100%', md: '100%' } }}>      
      <Stack spacing={1} direction="column">
        {/* 카메라 레이아웃 */}
        <Grid
          container
          spacing={1}
          columns={12}
          sx={{ 
            mb: (theme) => theme.spacing(1),
            mt: (theme) => theme.spacing(2)  // 상단 여백 추가
          }}
        >
          <CameraLayout
            activeCameras={activeCameras}
            cameraGridSizes={cameraGridSizes}
            layoutType={layoutType}
          />
        </Grid>

        {/* 카메라 제어 패널 */}
        <CameraControlPanel onCameraStateChange={handleCameraStateChange} />
      </Stack>
    </Box>
  );
}
