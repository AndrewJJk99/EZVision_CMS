import React from 'react';
import Grid from '@mui/material/Grid2';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import CameraSessions1 from './CameraSessions/CameraSessions1';
import CameraSessions2 from './CameraSessions/CameraSessions2';
import CameraSessions3 from './CameraSessions/CameraSessions3';
import CameraSessions4 from './CameraSessions/CameraSessions4';

const CameraLayout = ({ activeCameras, cameraGridSizes, layoutType }) => {
  // 활성화된 카메라 개수 계산
  const activeCameraCount = Object.values(activeCameras).filter(Boolean).length;
  
  // 카메라 세션 컴포넌트 매핑
  const cameraComponents = {
    1: CameraSessions1,
    2: CameraSessions2,
    3: CameraSessions3,
    4: CameraSessions4
  };

  // 활성화된 카메라가 없을 때
  if (layoutType === 'empty') {
    return (
      <Grid size={{ xs: 8, md: 10 }}>
        <Box sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '50vh',
          bgcolor: 'background.paper',
          borderRadius: 1,
          border: '1px dashed',
          borderColor: 'divider'
        }}>
          <Typography color="text.secondary" variant="h6">
            활성화된 카메라가 없습니다
          </Typography>
        </Box>
      </Grid>
    );
  }

  // 카메라 ID 순서대로 정렬하여 렌더링 (1, 2, 3, 4 순서 보장)
  const sortedActiveCameras = Object.entries(activeCameras)
    .filter(([_, isActive]) => isActive)
    .sort(([a], [b]) => parseInt(a) - parseInt(b));

  return (
    <>
      {sortedActiveCameras.map(([cameraId, isActive]) => {
        const CameraComponent = cameraComponents[cameraId];
        const gridSize = cameraGridSizes[cameraId];

        if (!CameraComponent || !gridSize) return null;

        // 모니터 개수에 따라 높이 조정
        // 1개일 때: 60vh (비율 줄임), 3개일 때: 45vh, 4개일 때: 45vh
        let boxHeight = '70vh';
        if (activeCameraCount === 1) {
          boxHeight = '70vh';  // 1개일 때 비율 줄임
        } else if (activeCameraCount === 3) {
          boxHeight = '35vh';
        } else if (activeCameraCount === 4) {
          boxHeight = '35vh';
        }

        return (
          <Grid key={cameraId} size={gridSize}>
            <Box sx={{
              height: boxHeight,  // 고정 높이 사용으로 모든 카메라 동일한 크기 보장
              bgcolor: 'background.paper',
              borderRadius: 1,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              pt: 0.2  // 상단 여백 최소화
            }}>
              <CameraComponent activeCameraCount={activeCameraCount} />
            </Box>
          </Grid>
        );
      })}
    </>
  );
};

export default CameraLayout;
