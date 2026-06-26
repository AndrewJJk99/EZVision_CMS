import * as React from 'react';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import TuneIcon from '@mui/icons-material/Tune';
import { CAMERA_OPTIONS } from './constants';
import LaserDetectSettings from './LaserDetectSettings';

export default function CmsSetupCard({
  title,
  description,
  laserInDialog = false,
  uiCamera,
  setUiCamera,
  calibrations,
  calibFile,
  setCalibFile,
  method,
  setMethod,
  blueBoost,
  setBlueBoost,
  threshOffset,
  setThreshOffset,
  hLow,
  setHLow,
  hHigh,
  setHHigh,
  sMin,
  setSMin,
  vMin,
  setVMin,
  bridgeGap,
  setBridgeGap,
  roiEnabled,
  setRoiEnabled,
  roiY,
  setRoiY,
  imgHeight,
  message,
  severity,
}) {
  const [laserDialogOpen, setLaserDialogOpen] = React.useState(false);

  const laserProps = {
    method,
    setMethod,
    blueBoost,
    setBlueBoost,
    threshOffset,
    setThreshOffset,
    hLow,
    setHLow,
    hHigh,
    setHHigh,
    sMin,
    setSMin,
    vMin,
    setVMin,
    bridgeGap,
    setBridgeGap,
    roiEnabled,
    setRoiEnabled,
    roiY,
    setRoiY,
    imgHeight,
  };

  const methodLabel = method === 'auto' ? '자동' : 'HSV';

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
          <Grid size={{ xs: 6, md: 2 }}>
            <TextField select fullWidth size="small" label="Camera" value={uiCamera} onChange={(e) => setUiCamera(Number(e.target.value))}>
              {CAMERA_OPTIONS.map((c) => (
                <MenuItem key={c.ui} value={c.ui}>
                  Camera {c.ui}
                </MenuItem>
              ))}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 5 }}>
            <TextField
              select
              fullWidth
              size="small"
              label="Calibration 결과"
              value={calibFile}
              onChange={(e) => setCalibFile(e.target.value)}
              helperText={
                calibrations.length
                  ? '왜곡 보정에 사용할 캘리브레이션'
                  : '저장된 캘리브레이션 없음 — Calibration 탭에서 먼저 실행'
              }
            >
              {calibrations.map((c) => (
                <MenuItem key={c.file} value={c.file}>
                  {`Cam${c.ui_camera_id ?? '-'} | RMS ${c.rms_error != null ? c.rms_error.toFixed(3) : '-'} | ${c.saved_at || c.file}`}
                </MenuItem>
              ))}
            </TextField>
          </Grid>
          {laserInDialog && (
            <Grid size={{ xs: 12, sm: 6, md: 5 }}>
              <Button
                variant="outlined"
                startIcon={<TuneIcon />}
                onClick={() => setLaserDialogOpen(true)}
                sx={{ height: 40, mt: { xs: 0, md: 0 } }}
              >
                레이저 검출 설정 ({methodLabel})
              </Button>
            </Grid>
          )}
        </Grid>

        {!laserInDialog && (
          <>
            <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 1, mt: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                레이저 검출 방식
              </Typography>
            </Stack>
            <LaserDetectSettings {...laserProps} />
          </>
        )}

        {message && (
          <Alert severity={severity} sx={{ mt: 2 }}>
            {message}
          </Alert>
        )}

        <Dialog open={laserDialogOpen} onClose={() => setLaserDialogOpen(false)} maxWidth="md" fullWidth>
          <DialogTitle>레이저 검출 설정</DialogTitle>
          <DialogContent dividers>
            <LaserDetectSettings {...laserProps} />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setLaserDialogOpen(false)} variant="contained">
              확인
            </Button>
          </DialogActions>
        </Dialog>
      </CardContent>
    </Card>
  );
}
