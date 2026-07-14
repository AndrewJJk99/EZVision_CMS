import * as React from 'react';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Grid from '@mui/material/Grid2';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Alert from '@mui/material/Alert';
import { CAMERA_OPTIONS } from './constants';

export default function CmsSetupCard({
  title,
  description,
  uiCamera,
  setUiCamera,
  calibrations,
  calibFile,
  setCalibFile,
  message,
  severity,
}) {
  return (
    <Card sx={{ minWidth: 0, overflow: 'hidden' }}>
      <CardContent sx={{ minWidth: 0 }}>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 0.5 }}>
          {title}
        </Typography>
        {description && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {description}
          </Typography>
        )}

        <Grid container spacing={2} columns={12} disableEqualOverflow sx={{ width: '100%', minWidth: 0, alignItems: 'flex-start' }}>
          <Grid size={{ xs: 12, sm: 4, md: 3 }}>
            <TextField select fullWidth size="small" label="Camera" value={uiCamera} onChange={(e) => setUiCamera(Number(e.target.value))}>
              {CAMERA_OPTIONS.map((c) => (
                <MenuItem key={c.ui} value={c.ui}>
                  Camera {c.ui}
                </MenuItem>
              ))}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, sm: 8, md: 9 }}>
            <TextField
              select
              fullWidth
              size="small"
              label="Calibration 결과"
              value={calibFile}
              onChange={(e) => setCalibFile(e.target.value)}
              helperText={
                calibrations.length
                  ? '왜곡 보정·간격 mm/px에 사용할 캘리브레이션'
                  : '저장된 캘리브레이션 없음 — Calibration 탭에서 먼저 실행'
              }
            >
              {calibrations.map((c) => (
                <MenuItem key={c.file} value={c.file}>
                  {`Cam${c.ui_camera_id ?? '-'} | RMS ${c.rms_error != null ? c.rms_error.toFixed(3) : '-'}${
                    c.plane_scale?.mm_per_px != null ? ` | ${c.plane_scale.mm_per_px} mm/px` : ''
                  } | ${c.saved_at || c.file}`}
                </MenuItem>
              ))}
            </TextField>
          </Grid>
        </Grid>

        {message && (
          <Alert severity={severity} sx={{ mt: 2 }}>
            {message}
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
