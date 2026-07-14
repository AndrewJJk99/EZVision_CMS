import * as React from 'react';
import Box from '@mui/material/Box';
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
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import LinearProgress from '@mui/material/LinearProgress';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import {
  captureCalibrationSample,
  getCalibrationStatus,
  resetCalibrationSamples,
  runCalibration,
  saveCalibration,
  startCalibration,
  stopCalibration,
} from '../../../../services/camera.api';
import { listCalibrations, computeGapScale } from '../../../../services/measurement.api';
import { useCalibrationForCamera } from '../context/CalibrationContext';

const CAMERA_OPTIONS = [
  { ui: 1, backend: 0 },
  { ui: 2, backend: 1 },
  { ui: 3, backend: 2 },
  { ui: 4, backend: 3 },
];

const MODEL_OPTIONS = [
  { value: 'brown5', label: 'Brown (k1~k3)' },
  { value: 'rational', label: 'Rational (고왜곡 권장)' },
];

function qualityChipColor(level) {
  if (level === 'pass') return 'success';
  if (level === 'warn') return 'warning';
  return 'error';
}

export default function CalibrationPanel() {
  const [uiCamera, setUiCamera] = React.useState(1);
  const cameraIdBackend = uiCamera - 1;
  const { setCalibrationTarget } = useCalibrationForCamera(cameraIdBackend);

  const [innerCols, setInnerCols] = React.useState(3);
  const [innerRows, setInnerRows] = React.useState(3);
  const [squareMm, setSquareMm] = React.useState(20);
  const [distortionModel, setDistortionModel] = React.useState('brown5');
  const [fixAspectRatio, setFixAspectRatio] = React.useState(true);
  const [forceSave, setForceSave] = React.useState(false);
  const [sessionActive, setSessionActive] = React.useState(false);
  const [status, setStatus] = React.useState(null);
  const [result, setResult] = React.useState(null);
  const [message, setMessage] = React.useState('');
  const [captureBusy, setCaptureBusy] = React.useState(false);
  const captureBusyRef = React.useRef(false);
  const [savedCalibs, setSavedCalibs] = React.useState([]);
  const [planeCalibFile, setPlaneCalibFile] = React.useState('');
  const [planeScaleBusy, setPlaneScaleBusy] = React.useState(false);
  const [planeScaleMsg, setPlaneScaleMsg] = React.useState('');
  const [planeScalePreview, setPlaneScalePreview] = React.useState(null);

  const setPreviewBusy = React.useCallback((busy) => {
    try {
      window.dispatchEvent(new CustomEvent('calibrationCaptureBusy', { detail: { busy } }));
    } catch {
      // 프리뷰 일시정지 이벤트 실패가 캡처 요청 자체를 막으면 안 됩니다.
    }
  }, []);

  const refreshStatus = React.useCallback(async () => {
    try {
      const res = await getCalibrationStatus(cameraIdBackend);
      setStatus(res?.status || null);
    } catch (e) {
      setStatus(null);
    }
  }, [cameraIdBackend]);

  const refreshSavedCalibs = React.useCallback(async () => {
    try {
      const res = await listCalibrations();
      const items = (res?.calibrations || []).filter((c) => c.camera_id === cameraIdBackend);
      setSavedCalibs(items);
      setPlaneCalibFile((prev) => {
        if (prev && items.some((c) => c.file === prev)) return prev;
        return items[0]?.file || '';
      });
    } catch (_e) {
      setSavedCalibs([]);
      setPlaneCalibFile('');
    }
  }, [cameraIdBackend]);

  React.useEffect(() => {
    refreshStatus();
    const id = setInterval(refreshStatus, 1000);
    return () => clearInterval(id);
  }, [refreshStatus, sessionActive]);

  React.useEffect(() => {
    refreshSavedCalibs();
  }, [refreshSavedCalibs]);

  const qualityGuide = status?.quality_guide;
  const qualityReport = result?.quality_report || status?.quality_report;
  const poseRatio = qualityGuide?.pose_coverage?.ratio ?? 0;
  const canSave = status?.calibrated && (qualityReport?.pass || forceSave);

  const handleStart = async () => {
    try {
      const res = await startCalibration(cameraIdBackend, {
        inner_cols: innerCols,
        inner_rows: innerRows,
        square_size_mm: Number(squareMm),
        distortion_model: distortionModel,
        fix_aspect_ratio: fixAspectRatio,
      });
      setSessionActive(true);
      setCalibrationTarget(cameraIdBackend, true);
      setStatus(res?.status || null);
      setResult(null);
      setForceSave(false);
      setMessage('캘리브레이션 시작 — 중앙·가장자리·기울인 포즈를 골고루 촬영하세요');
    } catch (e) {
      setMessage(e?.data?.error || e.message);
    }
  };

  const handleStop = async () => {
    setSessionActive(false);
    setCalibrationTarget(cameraIdBackend, false);
    setMessage('캘리브레이션 모드 종료');
    try {
      await stopCalibration(cameraIdBackend);
      refreshStatus();
    } catch (e) {
      setMessage(e?.data?.error || e.message);
    }
  };

  const handleCapture = async () => {
    if (captureBusyRef.current) return;
    captureBusyRef.current = true;
    setCaptureBusy(true);
    setMessage('샘플 캡처 중...');
    setPreviewBusy(true);
    try {
      const res = await captureCalibrationSample(cameraIdBackend);
      setStatus(res?.status || null);
      setMessage(res?.message || '샘플 캡처');
    } catch (e) {
      setMessage(e?.data?.error || e?.message || '캡처 실패');
    } finally {
      captureBusyRef.current = false;
      setCaptureBusy(false);
      setPreviewBusy(false);
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
      const res = await saveCalibration(cameraIdBackend, forceSave);
      setMessage(`저장 완료: ${res?.path || ''}`);
      const base = res?.path ? String(res.path).split(/[/\\]/).pop() : '';
      await refreshSavedCalibs();
      if (base) setPlaneCalibFile(base);
    } catch (e) {
      setMessage(e?.data?.error || e.message);
    }
  };

  const handleReset = async () => {
    try {
      const res = await resetCalibrationSamples(cameraIdBackend);
      setStatus(res?.status || null);
      setResult(null);
      setForceSave(false);
      setMessage('샘플 초기화됨');
    } catch (e) {
      setMessage(e?.data?.error || e.message);
    }
  };

  const selectedPlaneCalib = React.useMemo(
    () => savedCalibs.find((c) => c.file === planeCalibFile) || null,
    [savedCalibs, planeCalibFile],
  );

  const handleComputePlaneScale = async () => {
    if (!planeCalibFile) {
      setPlaneScaleMsg('저장할 캘리브레이션 파일을 선택하세요.');
      return;
    }
    setPlaneScaleBusy(true);
    setPlaneScaleMsg('체커보드로 mm/px 계산 중…');
    setPlaneScalePreview(null);
    try {
      const pat = selectedPlaneCalib?.pattern_inner_corners;
      const res = await computeGapScale(cameraIdBackend, {
        calibration_file: planeCalibFile,
        inner_cols: Array.isArray(pat) ? Number(pat[0]) || innerCols : innerCols,
        inner_rows: Array.isArray(pat) ? Number(pat[1]) || innerRows : innerRows,
        square_size_mm: Number(selectedPlaneCalib?.square_size_mm ?? squareMm) || 20,
        save: true,
      });
      setPlaneScalePreview(res);
      setPlaneScaleMsg(
        res?.mm_per_px != null
          ? `저장 완료: ${res.mm_per_px} mm/px → ${res.attached_to || planeCalibFile}`
          : '계산 완료',
      );
      await refreshSavedCalibs();
    } catch (e) {
      setPlaneScaleMsg(e?.data?.error || e?.message || 'mm/px 계산 실패');
      if (e?.data?.image) setPlaneScalePreview(e.data);
    } finally {
      setPlaneScaleBusy(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 0.5 }}>
          Checkerboard Calibration
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Zhang + Brown/Rational 왜곡 모델. 프리뷰는 1280×720, <b>샘플 캡처만 원본 해상도</b> (8장+, 권장 12+).
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
          <Grid size={{ xs: 4, md: 1.5 }}>
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
          <Grid size={{ xs: 4, md: 1.5 }}>
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
          <Grid size={{ xs: 4, md: 1.5 }}>
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
          <Grid size={{ xs: 12, sm: 6, md: 2.5 }}>
            <TextField
              select
              fullWidth
              size="small"
              label="왜곡 모델"
              value={distortionModel}
              disabled={sessionActive}
              onChange={(e) => setDistortionModel(e.target.value)}
            >
              {MODEL_OPTIONS.map((m) => (
                <MenuItem key={m.value} value={m.value}>
                  {m.label}
                </MenuItem>
              ))}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <FormControlLabel
              control={
                <Checkbox
                  size="small"
                  checked={fixAspectRatio}
                  disabled={sessionActive}
                  onChange={(e) => setFixAspectRatio(e.target.checked)}
                />
              }
              label="fx≈fy 고정 (FIX_ASPECT_RATIO)"
            />
          </Grid>
        </Grid>

        {sessionActive && qualityGuide && (
          <BoxGuide qualityGuide={qualityGuide} poseRatio={poseRatio} />
        )}

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
              <Button
                variant="contained"
                onClick={handleCapture}
                sx={{ minWidth: 104 }}
              >
                {captureBusy ? '캡처 중' : '샘플 캡처'}
              </Button>
              <Button variant="contained" color="secondary" onClick={handleRun}>
                캘리브레이션 실행
              </Button>
              <Button variant="outlined" onClick={handleSave} disabled={!canSave}>
                결과 저장
              </Button>
              <Button variant="text" onClick={handleReset}>
                샘플 초기화
              </Button>
            </>
          )}
        </Stack>

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
          <Chip
            label={`검출: ${status?.detected ? 'OK' : '대기'}`}
            color={status?.detected ? 'success' : 'default'}
            size="small"
          />
          <Chip
            label={`샘플 ${status?.sample_count ?? 0} / ${status?.min_samples ?? 8}+ (권장 ${status?.recommended_samples ?? 12})`}
            size="small"
          />
          {status?.distortion_model && (
            <Chip size="small" label={status.distortion_model} variant="outlined" />
          )}
          {status?.rms_error != null && (
            <Chip label={`RMS ${status.rms_error.toFixed(4)} px`} color="info" size="small" />
          )}
          {qualityReport && (
            <Chip
              label={qualityReport.level?.toUpperCase() || '—'}
              color={qualityChipColor(qualityReport.level)}
              size="small"
            />
          )}
        </Stack>

        {qualityReport && !qualityReport.pass && status?.calibrated && (
          <FormControlLabel
            sx={{ mb: 1 }}
            control={
              <Checkbox
                size="small"
                checked={forceSave}
                onChange={(e) => setForceSave(e.target.checked)}
              />
            }
            label="품질 미달 — 강제 저장 (WARN/FAIL)"
          />
        )}

        {qualityReport?.issues?.length > 0 && (
          <Alert severity={qualityChipColor(qualityReport.level)} sx={{ mb: 1, py: 0.5 }}>
            {qualityReport.issues.join(' · ')}
          </Alert>
        )}

        {result?.all_per_view_errors?.length > 0 && (
          <PerViewTable
            errors={result.all_per_view_errors}
            excluded={result.excluded_sample_indices || []}
          />
        )}

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
            {result.excluded_sample_indices?.length > 0 && (
              <> · outlier 제외: {result.excluded_sample_indices.map((i) => `#${i + 1}`).join(', ')}</>
            )}
          </Alert>
        )}

        <Box sx={{ mt: 2.5, pt: 2, borderTop: 1, borderColor: 'divider' }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.5 }}>
            작업거리 평면 스케일 (간격용)
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            측정면과 <b>같은 거리</b>에 체커보드를 두고 mm/px를 계산합니다.
            결과는 선택한 캘리브레이션 파일에 <code>plane_scale</code>로 함께 저장되며,
            간격 탭에서 해당 캘리브를 고르면 자동 적용됩니다.
          </Typography>
          <Grid container spacing={1.5} columns={12} alignItems="center">
            <Grid size={{ xs: 12, md: 7 }}>
              <TextField
                select
                fullWidth
                size="small"
                label="캘리브레이션 파일"
                value={planeCalibFile}
                onChange={(e) => setPlaneCalibFile(e.target.value)}
                helperText={
                  savedCalibs.length
                    ? '스케일을 붙일 저장된 캘리브레이션'
                    : '저장된 캘리브레이션 없음 — 먼저 결과 저장'
                }
              >
                {savedCalibs.map((c) => (
                  <MenuItem key={c.file} value={c.file}>
                    {c.file}
                    {c.plane_scale?.mm_per_px != null
                      ? ` · ${c.plane_scale.mm_per_px} mm/px`
                      : ' · 스케일 없음'}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, md: 5 }}>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                <Button
                  variant="contained"
                  color="secondary"
                  onClick={handleComputePlaneScale}
                  disabled={planeScaleBusy || !planeCalibFile || sessionActive}
                >
                  {planeScaleBusy ? '계산 중…' : 'mm/px 계산·저장'}
                </Button>
                {selectedPlaneCalib?.plane_scale?.mm_per_px != null && (
                  <Chip
                    size="small"
                    color="success"
                    label={`${selectedPlaneCalib.plane_scale.mm_per_px} mm/px`}
                  />
                )}
              </Stack>
            </Grid>
          </Grid>
          {planeScaleMsg && (
            <Alert
              severity={planeScaleMsg.includes('실패') || planeScaleMsg.includes('없') ? 'warning' : 'info'}
              sx={{ mt: 1, py: 0.5 }}
            >
              {planeScaleMsg}
            </Alert>
          )}
          {planeScalePreview?.image && (
            <Box
              component="img"
              src={planeScalePreview.image}
              alt="plane scale preview"
              sx={{ mt: 1, maxWidth: '100%', maxHeight: 220, borderRadius: 1, display: 'block' }}
            />
          )}
        </Box>
      </CardContent>
    </Card>
  );
}

function BoxGuide({ qualityGuide, poseRatio }) {
  return (
    <Stack spacing={0.5} sx={{ mt: 1.5, p: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
      <Typography variant="caption" color="text.secondary">
        포즈 커버리지: {qualityGuide.pose_coverage?.missing_hint || '—'}
      </Typography>
      <LinearProgress
        variant="determinate"
        value={Math.min(100, poseRatio * 100)}
        sx={{ height: 6, borderRadius: 1 }}
      />
      {qualityGuide.last_sample_warnings?.length > 0 && (
        <Typography variant="caption" color="warning.main">
          최근 샘플: {qualityGuide.last_sample_warnings.join(' · ')}
        </Typography>
      )}
    </Stack>
  );
}

function PerViewTable({ errors, excluded }) {
  return (
    <Box sx={{ maxHeight: 140, overflow: 'auto', mb: 1 }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>샘플</TableCell>
            <TableCell align="right">reproj (px)</TableCell>
            <TableCell>상태</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {errors.map((err, i) => (
            <TableRow key={i} sx={{ opacity: excluded.includes(i) ? 0.5 : 1 }}>
              <TableCell>#{i + 1}</TableCell>
              <TableCell align="right">{err.toFixed(4)}</TableCell>
              <TableCell>
                {excluded.includes(i) ? (
                  <Chip size="small" label="제외" color="warning" />
                ) : (
                  <Chip size="small" label="사용" color="success" variant="outlined" />
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
