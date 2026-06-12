import React from 'react';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Grid from '@mui/material/Grid2';

import { useCameraApp } from '../context/CameraAppContext';
import { useCameraLayout } from './CameraGrid/hooks/useCameraLayout';
import { CalibrationProvider } from './CameraGrid/context/CalibrationContext';
import CameraLayout from './CameraGrid/components/CameraLayout';
import CameraMonitorControl from './CameraGrid/components/CameraControls/CameraMonitorControl';
import CalibrationPanel from './CameraGrid/components/CalibrationPanel';

export default function CameraGrid() {
  const { activeCameras, handleCameraStateChange } = useCameraApp();
  const activeCameraCount = Object.values(activeCameras).filter(Boolean).length;
  const firstActiveCamera = Object.entries(activeCameras).find(([, v]) => v)?.[0];

  const { cameraGridSizes, layoutType } = useCameraLayout(
    activeCameras,
    activeCameraCount,
    firstActiveCamera,
  );

  return (
    <CalibrationProvider>
      <Box sx={{ width: '100%', maxWidth: '100%' }}>
        <Stack spacing={1} direction="column">
          <Grid container spacing={1} columns={12} sx={{ mb: 1 }}>
            <Grid size={{ xs: 12, lg: 4 }}>
              <CameraMonitorControl onCameraStateChange={handleCameraStateChange} />
            </Grid>
          </Grid>

          <Grid
            container
            spacing={1}
            columns={12}
            sx={{ mb: (theme) => theme.spacing(1) }}
          >
            <CameraLayout
              activeCameras={activeCameras}
              cameraGridSizes={cameraGridSizes}
              layoutType={layoutType}
            />
          </Grid>

          <CalibrationPanel />
        </Stack>
      </Box>
    </CalibrationProvider>
  );
}
