import React from 'react';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Grid from '@mui/material/Grid2';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Divider from '@mui/material/Divider';
import Typography from '@mui/material/Typography';

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
      <Box sx={{ width: '100%', maxWidth: '100%', minWidth: 0 }}>
        <Stack spacing={1} direction="column">
          <Card sx={{ minWidth: 0, overflow: 'hidden' }}>
            <CardContent sx={{ p: { xs: 1, md: 1.5 }, '&:last-child': { pb: { xs: 1, md: 1.5 } } }}>
              <CameraMonitorControl onCameraStateChange={handleCameraStateChange} />

              <Divider sx={{ my: 1 }} />

              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                Camera
              </Typography>

              <Grid container spacing={1} columns={12} disableEqualOverflow sx={{ minWidth: 0 }}>
                <CameraLayout
                  activeCameras={activeCameras}
                  cameraGridSizes={cameraGridSizes}
                  layoutType={layoutType}
                />
              </Grid>
            </CardContent>
          </Card>

          <CalibrationPanel />
        </Stack>
      </Box>
    </CalibrationProvider>
  );
}
