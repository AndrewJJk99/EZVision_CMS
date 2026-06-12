import * as React from 'react';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Grid from '@mui/material/Grid2';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import {
  captureCalibrationSample,
  getCalibrationStatus,
  resetCalibrationSamples,
  runCalibration,
  saveCalibration,
  startCalibration,
  stopCalibration,
} from '../../../../services/camera.api';
import { useCalibrationForCamera } from '../context/CalibrationContext';

const CAMERA_OPTIONS = [
  { ui: 1, backend: 0 },
  { ui: 2, backend: 1 },
  { ui: 3, backend: 2 },
  { ui: 4, backend: 3 },
];

export default function CalibrationPanel() {
  const [uiCamera, setUiCamera] = React.useState(1);
  const cameraIdBackend = uiCamera - 1;
  const { setCalibrationTarget } = useCalibrationForCamera(cameraIdBackend);

  const [innerCols, setInnerCols] = React.useState(3);
  const [innerRows, setInnerRows] = React.useState(3);
  const [squareMm, setSquareMm] = React.useState(20);
  const [sessionActive, setSessionActive] = React.useState(false);
  const [status, setStatus] = React.useState(null);
  const [result, setResult] = React.useState(null);
  const [message, setMessage] = React.useState('');

  const refreshStatus = React.useCallback(async () => {
    try {
      const res = await getCalibrationStatus(cameraIdBackend);
      setStatus(res?.status || null);
    } catch (e) {
      setStatus(null);
    }
  }, [cameraIdBackend]);

  React.useEffect(() => {
    refreshStatus();
    const id = setInterval(refreshStatus, 1000);
    return () => clearInterval(id);
  }, [refreshStatus, sessionActive]);

  const handleStart = async () => {
    try {
      const res = await startCalibration(cameraIdBackend, {
        inner_cols: innerCols,
        inner_rows: innerRows,
        square_size_mm: Number(squareMm),
      });
      setSessionActive(true);
      setCalibrationTarget(cameraIdBackend, true);
      setStatus(res?.status || null);
      setResult(null);
      setMessage('캘리브레이션 모드 시작 — 모니터 화면에서 체커보드 코너를 확인하세요');
    } catch (e) {
      setMessage(e?.data?.error || e.message);
    }
  };

  const handleStop = async () => {
    try {
      await stopCalibration(cameraIdBackend);
      setSessionActive(false);
      setCalibrationTarget(cameraIdBackend, false);
      setMessage('캘리브레이션 모드 종료');
      refreshStatus();
    } catch (e) {
      setMessage(e?.data?.error || e.message);
    }
  };

  const handleCapture = async () => {
    try {
      const res = await captureCalibrationSample(cameraIdBackend);
      setStatus(res?.status || null);
      setMessage(res?.message || '샘플 캡처');
    } catch (e) {
      setMessage(e?.data?.error || e?.message || '캡처 실패');
    }
  };

  const handleRun = async () => {
    try {
      const res = await runCalibration(cameraIdBackend);
      setResult(res);
      setStatus(res?.status || null);
      setMessage(res?.message || '캘리브레이션 완료');
    } catch (e) {
      setMessage(e?.data?.error || e?.message || '캘리브레이션 실패');
    }
  };

  const handleSave = async () => {
    try {
      const res = await saveCalibration(cameraIdBackend);
      setMessage(`저장 완료: ${res?.path || ''}`);
    } catch (e) {
      setMessage(e?.data?.error || e.message);
    }
  };

  const handleReset = async () => {
    try {
      const res = await resetCalibrationSamples(cameraIdBackend);
      setStatus(res?.status || null);
      setResult(null);
      setMessage('샘플 초기화됨');
    } catch (e) {
      setMessage(e?.data?.error || e.message);
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
          Checkerboard Calibration
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          20mm 정사각형 체커보드 (기본 4×4 칸 → 내부 코너 3×3). Zhang&apos;s method로 왜곡 보정.
          시작 후 모니터 화면에 코너가 실시간 표시됩니다.
        </Typography>

        <Grid container spacing={2} columns={12}>
          <Grid size={{ xs: 12, md: 2 }}>
            <TextField
              select
              fullWidth
              size="small"
              label="Camera"
              value={uiCamera}
              disabled={sessionActive}
              onChange={(e) => setUiCamera(Number(e.target.value))}
            >
              {CAMERA_OPTIONS.map((c) => (
                <MenuItem key={c.ui} value={c.ui}>
                  Camera {c.ui}
                </MenuItem>
              ))}
            </TextField>
          </Grid>
          <Grid size={{ xs: 4, md: 2 }}>
            <TextField
              fullWidth
              size="small"
              type="number"
              label="Inner cols"
              value={innerCols}
              disabled={sessionActive}
              onChange={(e) => setInnerCols(Number(e.target.value))}
            />
          </Grid>
          <Grid size={{ xs: 4, md: 2 }}>
            <TextField
              fullWidth
              size="small"
              type="number"
              label="Inner rows"
              value={innerRows}
              disabled={sessionActive}
              onChange={(e) => setInnerRows(Number(e.target.value))}
            />
          </Grid>
          <Grid size={{ xs: 4, md: 2 }}>
            <TextField
              fullWidth
              size="small"
              type="number"
              label="Square (mm)"
              value={squareMm}
              disabled={sessionActive}
              onChange={(e) => setSquareMm(Number(e.target.value))}
            />
          </Grid>
        </Grid>

        <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 2, mb: 1 }}>
          {!sessionActive ? (
            <Button variant="contained" onClick={handleStart}>
              시작
            </Button>
          ) : (
            <>
              <Button variant="outlined" color="warning" onClick={handleStop}>
                종료
              </Button>
              <Button variant="contained" onClick={handleCapture}>
                샘플 캡처
              </Button>
              <Button variant="contained" color="secondary" onClick={handleRun}>
                캘리브레이션 실행
              </Button>
              <Button variant="outlined" onClick={handleSave} disabled={!status?.calibrated}>
                결과 저장
              </Button>
              <Button variant="text" onClick={handleReset}>
                샘플 초기화
              </Button>
            </>
          )}
        </Stack>

        <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
          <Chip
            label={`검출: ${status?.detected ? 'OK' : '대기'}`}
            color={status?.detected ? 'success' : 'default'}
            size="small"
          />
          <Chip
            label={`샘플 ${status?.sample_count ?? 0} / ${status?.min_samples ?? 8}+`}
            size="small"
          />
          {status?.rms_error != null && (
            <Chip label={`RMS ${status.rms_error.toFixed(4)} px`} color="info" size="small" />
          )}
        </Stack>

        {message && (
          <Alert severity="info" sx={{ mb: 1 }}>
            {message}
          </Alert>
        )}

        {result?.success && (
          <Alert severity="success">
            fx={result.focal_length_px?.fx?.toFixed(1)}, fy={result.focal_length_px?.fy?.toFixed(1)}
            {' | '}
            cx={result.principal_point_px?.cx?.toFixed(1)}, cy={result.principal_point_px?.cy?.toFixed(1)}
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
