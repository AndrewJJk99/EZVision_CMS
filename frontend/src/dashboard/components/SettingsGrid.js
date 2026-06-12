import React from 'react';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import CameraControl3 from './CameraGrid/components/CameraControls/CameraControl3';

export default function SettingsGrid() {
  return (
    <Box sx={{ width: '100%', maxWidth: '100%' }}>
      <Stack spacing={1}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          Camera Settings
        </Typography>
        <Typography variant="body2" color="text.secondary">
          카메라 feature, IP 매핑, 디바이스 설정
        </Typography>
        <CameraControl3 />
      </Stack>
    </Box>
  );
}
