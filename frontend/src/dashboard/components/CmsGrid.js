import * as React from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Button from '@mui/material/Button';
import Slider from '@mui/material/Slider';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';

import {
  listCalibrations,
  detectLaser,
  buildLut,
  getLut,
  measureStep,
  measureSteps,
} from '../../services/measurement.api';

const CAMERA_OPTIONS = [
  { ui: 1, backend: 0 },
  { ui: 2, backend: 1 },
  { ui: 3, backend: 2 },
  { ui: 4, backend: 3 },
];

export default function CmsGrid() {
  const [uiCamera, setUiCamera] = React.useState(1);
  const cameraIdBackend = uiCamera - 1;

  const [calibrations, setCalibrations] = React.useState([]);
  const [calibFile, setCalibFile] = React.useState('');
  const [mode, setMode] = React.useState(0);

  // 검출 방식
  const [method, setMethod] = React.useState('auto');
  const [blueBoost, setBlueBoost] = React.useState(true);
  const [threshOffset, setThreshOffset] = React.useState(0);
  const [hLow, setHLow] = React.useState(90);
  const [hHigh, setHHigh] = React.useState(130);
  const [sMin, setSMin] = React.useState(80);
  const [vMin, setVMin] = React.useState(80);
  const [bridgeGap, setBridgeGap] = React.useState(25);
  const [roiEnabled, setRoiEnabled] = React.useState(false);
  const [roiY, setRoiY] = React.useState([0, 720]);

  // 결과 표시
  const [resultImage, setResultImage] = React.useState(null);
  const [imgWidth, setImgWidth] = React.useState(1280);
  const [imgHeight, setImgHeight] = React.useState(720);
  const [detectInfo, setDetectInfo] = React.useState(null);

  // LUT
  const [incrementMm, setIncrementMm] = React.useState(2.5);
  const [baseMm, setBaseMm] = React.useState(0);
  const [reverseOrder, setReverseOrder] = React.useState(false);
  const [stepSensitivity, setStepSensitivity] = React.useState(50);
  const [lutTable, setLutTable] = React.useState(null);

  // 측정
  const [aRange, setARange] = React.useState([100, 300]);
  const [bRange, setBRange] = React.useState([900, 1100]);
  const [measureResult, setMeasureResult] = React.useState(null);
  const [stepResult, setStepResult] = React.useState(null);

  const [lutInfo, setLutInfo] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [message, setMessage] = React.useState('');
  const [severity, setSeverity] = React.useState('info');

  const detectionPayload = React.useCallback(
    () => ({
      method,
      blue_boost: blueBoost,
      thresh_offset: threshOffset,
      h_low: hLow,
      h_high: hHigh,
      s_min: sMin,
      v_min: vMin,
      keep_largest: true,
      bridge_gap: bridgeGap,
      roi_y0: roiEnabled ? roiY[0] : null,
      roi_y1: roiEnabled ? roiY[1] : null,
    }),
    [method, blueBoost, threshOffset, hLow, hHigh, sMin, vMin, bridgeGap, roiEnabled, roiY],
  );

  const refreshCalibrations = React.useCallback(async () => {
    try {
      const res = await listCalibrations();
      const items = res?.calibrations || [];
      setCalibrations(items);
      if (items.length && !calibFile) {
        const forCamera = items.find((c) => c.camera_id === cameraIdBackend);
        setCalibFile((forCamera || items[0]).file);
      }
    } catch (e) {
      setSeverity('warning');
      setMessage(e?.data?.error || e?.message || '캘리브레이션 목록 조회 실패');
    }
  }, [calibFile, cameraIdBackend]);

  const refreshLut = React.useCallback(async () => {
    try {
      setLutInfo(await getLut(cameraIdBackend));
    } catch (e) {
      setLutInfo(null);
    }
  }, [cameraIdBackend]);

  React.useEffect(() => {
    refreshCalibrations();
  }, [refreshCalibrations]);

  React.useEffect(() => {
    refreshLut();
  }, [refreshLut]);

  const applySize = (res) => {
    const w = res?.image_size?.width;
    const h = res?.image_size?.height;
    if (w) setImgWidth(w);
    if (h) {
      setImgHeight(h);
      if (!roiEnabled) setRoiY([0, h]);
    }
  };

  const run = async (fn, okMsg) => {
    setLoading(true);
    setMessage('');
    try {
      const res = await fn();
      setSeverity('success');
      setMessage(okMsg);
      return res;
    } catch (e) {
      setSeverity('error');
      setMessage(e?.data?.error || e?.message || '요청 실패');
      return null;
    } finally {
      setLoading(false);
    }
  };

  const handleCaptureDetect = async () => {
    const res = await run(
      () => detectLaser(cameraIdBackend, { calibration_file: calibFile || null, use_stored: false, ...detectionPayload() }),
      '캡처 & 검출 완료 (가장 긴 선만 자동 추출)',
    );
    if (res) {
      setResultImage(res.image);
      setDetectInfo(res);
      applySize(res);
    }
  };

  const handleRedetect = async () => {
    const res = await run(
      () => detectLaser(cameraIdBackend, { calibration_file: calibFile || null, use_stored: true, ...detectionPayload() }),
      '재검출 완료 (같은 이미지)',
    );
    if (res) {
      setResultImage(res.image);
      setDetectInfo(res);
      applySize(res);
    }
  };

  const handleBuildLut = async () => {
    const res = await run(
      () => buildLut(cameraIdBackend, {
        increment_mm: incrementMm,
        base_mm: baseMm,
        reverse_order: reverseOrder,
        sensitivity: stepSensitivity,
      }),
      'LUT 생성 및 저장 완료',
    );
    if (res) {
      setLutTable(res.table || null);
      if (res.image) setResultImage(res.image);
      refreshLut();
    }
  };

  const handleMeasureSteps = async () => {
    const res = await run(
      () => measureSteps(cameraIdBackend, { reverse_order: reverseOrder, sensitivity: stepSensitivity }),
      '자동 단 분석 완료',
    );
    if (res) {
      setStepResult(res);
      if (res.image) setResultImage(res.image);
    }
  };

  const handleMeasure = async () => {
    const res = await run(
      () => measureStep(cameraIdBackend, { a_x0: aRange[0], a_x1: aRange[1], b_x0: bRange[0], b_x1: bRange[1] }),
      'A/B 단차 측정 완료',
    );
    if (res) {
      setMeasureResult(res);
      if (res.image) setResultImage(res.image);
    }
  };

  const sliderRow = (label, value, setter, min, max, step = 1) => (
    <Grid size={{ xs: 6, md: 3 }}>
      <Typography variant="body2" gutterBottom>
        {label}: {value}
      </Typography>
      <Slider value={value} min={min} max={max} step={step} onChange={(_, v) => setter(v)} size="small" />
    </Grid>
  );

  return (
    <Box sx={{ width: '100%', maxWidth: '100%' }}>
      <Stack spacing={1.5}>
        <Card>
          <CardContent>
            <Typography variant="h6" sx={{ fontWeight: 600, mb: 0.5 }}>
              CMS — 라인 레이저 단차(높이차) 측정
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              검출 시 <b>점으로 이어진 가장 긴 선 하나만</b> 자동으로 남기고 반사는 버립니다(수동 편집 없음).
              ① 레이저 튜닝·② LUT 만들기는 같은 캡처 이미지를 사용하고, ③ 측정은 새 대상을 캡처합니다.
            </Typography>

            <Grid container spacing={2} columns={12}>
              <Grid size={{ xs: 6, md: 2 }}>
                <TextField select fullWidth size="small" label="Camera" value={uiCamera} onChange={(e) => setUiCamera(Number(e.target.value))}>
                  {CAMERA_OPTIONS.map((c) => (
                    <MenuItem key={c.ui} value={c.ui}>
                      Camera {c.ui}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, md: 7 }}>
                <TextField
                  select
                  fullWidth
                  size="small"
                  label="Calibration 결과"
                  value={calibFile}
                  onChange={(e) => setCalibFile(e.target.value)}
                  helperText={calibrations.length ? '카메라에 맞는 캘리브레이션 선택' : '저장된 캘리브레이션 없음 — Calibration 탭에서 먼저 실행'}
                >
                  {calibrations.map((c) => (
                    <MenuItem key={c.file} value={c.file}>
                      {`Cam${c.ui_camera_id ?? '-'} | RMS ${c.rms_error != null ? c.rms_error.toFixed(3) : '-'} | ${c.saved_at || c.file}`}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, md: 3 }}>
                <Stack direction="row" spacing={1} sx={{ height: '100%', alignItems: 'center' }}>
                  <Button variant="outlined" onClick={refreshCalibrations} size="small">
                    새로고침
                  </Button>
                  <Chip size="small" color={lutInfo ? 'success' : 'default'} label={lutInfo ? `LUT 있음 (${lutInfo.step_count ?? lutInfo.table?.length ?? '-'}단)` : 'LUT 없음'} />
                </Stack>
              </Grid>
            </Grid>

            <Divider sx={{ my: 2 }} />

            <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                레이저 검출 방식
              </Typography>
              <TextField select size="small" value={method} onChange={(e) => setMethod(e.target.value)} sx={{ minWidth: 200 }}>
                <MenuItem value="auto">자동(밝은 곳 찾기) — 추천</MenuItem>
                <MenuItem value="hsv">색상(파란색 HSV) — 수동</MenuItem>
              </TextField>
            </Stack>

            {method === 'auto' ? (
              <Grid container spacing={3} columns={12} sx={{ alignItems: 'center' }}>
                {sliderRow('민감도 보정(±)', threshOffset, setThreshOffset, -60, 60)}
                {sliderRow('선 잇기 간격(px)', bridgeGap, setBridgeGap, 1, 200)}
                <Grid size={{ xs: 6, md: 3 }}>
                  <FormControlLabel control={<Switch checked={blueBoost} onChange={(e) => setBlueBoost(e.target.checked)} />} label="파란색 우선" />
                </Grid>
                <Grid size={{ xs: 6, md: 3 }}>
                  <FormControlLabel control={<Switch checked={roiEnabled} onChange={(e) => setRoiEnabled(e.target.checked)} />} label="ROI 밴드 사용" />
                </Grid>
              </Grid>
            ) : (
              <Grid container spacing={3} columns={12}>
                {sliderRow('H low', hLow, setHLow, 0, 179)}
                {sliderRow('H high', hHigh, setHHigh, 0, 179)}
                {sliderRow('S min', sMin, setSMin, 0, 255)}
                {sliderRow('V min', vMin, setVMin, 0, 255)}
                {sliderRow('선 잇기 간격(px)', bridgeGap, setBridgeGap, 1, 200)}
                <Grid size={{ xs: 6, md: 3 }}>
                  <FormControlLabel control={<Switch checked={roiEnabled} onChange={(e) => setRoiEnabled(e.target.checked)} />} label="ROI 밴드 사용" />
                </Grid>
              </Grid>
            )}
            {roiEnabled && (
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" gutterBottom>
                  레이저가 지나는 세로 구간 Y: {roiY[0]} ~ {roiY[1]}
                </Typography>
                <Slider value={roiY} min={0} max={imgHeight} onChange={(_, v) => setRoiY(v)} valueLabelDisplay="auto" sx={{ color: 'secondary.main' }} />
              </Box>
            )}

            {message && (
              <Alert severity={severity} sx={{ mt: 2 }}>
                {message}
              </Alert>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent sx={{ pb: 1 }}>
            <Tabs value={mode} onChange={(_, v) => setMode(v)} sx={{ mb: 2 }}>
              <Tab label="① 레이저 튜닝" />
              <Tab label="② LUT 만들기" />
              <Tab label="③ 측정" />
            </Tabs>

            {mode === 0 && (
              <Stack spacing={1.5}>
                <Typography variant="body2" color="text.secondary">
                  "캡처 & 검출"을 누르면 한 장을 찍고 가장 긴 레이저 선만 자동으로 추출합니다. 선이 끊겨
                  나오면 "선 잇기 간격"을 키우고, 반사가 더 길게 잡히면 ROI 밴드로 범위를 제한하세요.
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Button variant="contained" onClick={handleCaptureDetect} disabled={loading || !calibFile}>
                    {loading ? '처리 중…' : '캡처 & 검출'}
                  </Button>
                  <Button variant="outlined" onClick={handleRedetect} disabled={loading || !resultImage}>
                    재검출(같은 이미지)
                  </Button>
                  {detectInfo?.coverage != null && (
                    <Chip
                      size="small"
                      color={detectInfo.coverage > 0.5 ? 'success' : 'warning'}
                      label={`검출 ${detectInfo.valid_columns}/${detectInfo.total_columns} (${(detectInfo.coverage * 100).toFixed(1)}%)`}
                    />
                  )}
                </Stack>
              </Stack>
            )}

            {mode === 1 && (
              <Stack spacing={1.5}>
                <Typography variant="body2" color="text.secondary">
                  ① 튜닝에서 캡처한 같은 이미지로 LUT를 만듭니다. <b>계단 수는 자동으로 찾고</b>, 각 단에
                  0, {incrementMm}, {incrementMm * 2}… mm 를 순서대로 매깁니다. (개수는 입력하지 않습니다)
                </Typography>
                <Grid container spacing={2} columns={12}>
                  <Grid size={{ xs: 6, md: 4 }}>
                    <TextField type="number" size="small" fullWidth label="단 높이 증가(mm)" value={incrementMm} onChange={(e) => setIncrementMm(Number(e.target.value))} />
                  </Grid>
                  <Grid size={{ xs: 6, md: 4 }}>
                    <TextField type="number" size="small" fullWidth label="기준 높이(mm)" value={baseMm} onChange={(e) => setBaseMm(Number(e.target.value))} />
                  </Grid>
                  <Grid size={{ xs: 6, md: 4 }}>
                    <FormControlLabel control={<Switch checked={reverseOrder} onChange={(e) => setReverseOrder(e.target.checked)} />} label="높이 순서 반전" />
                  </Grid>
                  <Grid size={{ xs: 12 }}>
                    <Typography variant="body2" gutterBottom>
                      단 검출 민감도: {stepSensitivity} (높을수록 작은 단차도 분리)
                    </Typography>
                    <Slider value={stepSensitivity} min={0} max={100} onChange={(_, v) => setStepSensitivity(v)} valueLabelDisplay="auto" />
                  </Grid>
                </Grid>
                <Button variant="contained" onClick={handleBuildLut} disabled={loading || !detectInfo}>
                  {loading ? '생성 중…' : 'LUT 생성/저장'}
                </Button>
                {lutTable && (
                  <Box sx={{ maxHeight: 220, overflow: 'auto' }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>단</TableCell>
                          <TableCell align="right">높이(mm)</TableCell>
                          <TableCell align="right">y(px)</TableCell>
                          <TableCell align="right">x(px)</TableCell>
                          <TableCell align="right">픽셀수</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {lutTable.map((r, i) => (
                          <TableRow key={i}>
                            <TableCell>{i + 1}</TableCell>
                            <TableCell align="right">{r.height_mm}</TableCell>
                            <TableCell align="right">{r.y_pixel}</TableCell>
                            <TableCell align="right">{r.mean_x}</TableCell>
                            <TableCell align="right">{r.count}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                )}
              </Stack>
            )}

            {mode === 2 && (
              <Stack spacing={1.5}>
                <Typography variant="body2" color="text.secondary">
                  측정할 <b>실제 대상</b>을 새로 캡처한 뒤 저장된 LUT로 높이를 환산합니다.
                  (LUT는 한 번 만들면 재사용 — 카메라·레이저 고정 필수)
                </Typography>
                {!lutInfo && (
                  <Alert severity="warning" sx={{ py: 0.5 }}>
                    저장된 LUT가 없습니다. ② LUT 만들기에서 먼저 생성하세요.
                  </Alert>
                )}
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }} flexWrap="wrap" useFlexGap>
                  <Button variant="contained" onClick={handleCaptureDetect} disabled={loading || !calibFile}>
                    {loading ? '처리 중…' : '측정 대상 캡처 & 검출'}
                  </Button>
                  {detectInfo?.coverage != null && (
                    <Chip size="small" label={`검출 ${detectInfo.valid_columns}/${detectInfo.total_columns}`} />
                  )}
                </Stack>

                <Divider textAlign="left">
                  <Chip size="small" label="자동 단 분석 (계단/다단 대상)" />
                </Divider>
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }} flexWrap="wrap" useFlexGap>
                  <Button variant="contained" onClick={handleMeasureSteps} disabled={loading || !lutInfo || !detectInfo}>
                    {loading ? '분석 중…' : '자동 단 분석'}
                  </Button>
                  <Typography variant="body2" color="text.secondary">
                    계단 수는 자동 검출 (개수 입력 없음)
                  </Typography>
                  {stepResult?.steps && <Chip size="small" label={`검출된 단: ${stepResult.steps.length}`} />}
                </Stack>
                {stepResult?.steps && (
                  <Alert severity="info" sx={{ py: 0.5 }}>
                    LUT 사용: {stepResult.lut_file || '-'}
                    {stepResult.lut_y_range && (
                      <>
                        {' '}
                        | LUT y범위 {stepResult.lut_y_range.y_min?.toFixed(1)}~
                        {stepResult.lut_y_range.y_max?.toFixed(1)} px → 높이{' '}
                        {stepResult.lut_y_range.h_min}~{stepResult.lut_y_range.h_max} mm
                      </>
                    )}
                    {stepResult.used_sensitivity != null && (
                      <> | 단 검출 민감도 {stepResult.used_sensitivity}</>
                    )}
                  </Alert>
                )}
                {stepResult?.steps && (
                  <Box sx={{ maxHeight: 240, overflow: 'auto' }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>단</TableCell>
                          <TableCell align="right">높이(mm)</TableCell>
                          <TableCell align="right">이전 단과 차이(mm)</TableCell>
                          <TableCell align="right">y(px)</TableCell>
                          <TableCell align="right">x(px)</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {stepResult.steps.map((s, i) => (
                          <TableRow key={s.index}>
                            <TableCell>{s.index}</TableCell>
                            <TableCell align="right">{s.height_mm}</TableCell>
                            <TableCell align="right">{i === 0 ? '-' : stepResult.diffs[i - 1]}</TableCell>
                            <TableCell align="right">{s.y_pixel}</TableCell>
                            <TableCell align="right">{s.mean_x}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                )}

                <Divider textAlign="left">
                  <Chip size="small" label="A/B 두 구간 단차" />
                </Divider>
                <Box>
                  <Typography variant="body2" gutterBottom>
                    A 구간 X: {aRange[0]} ~ {aRange[1]}
                  </Typography>
                  <Slider value={aRange} min={0} max={imgWidth} onChange={(_, v) => setARange(v)} valueLabelDisplay="auto" sx={{ color: 'success.main' }} />
                  <Typography variant="body2" gutterBottom>
                    B 구간 X: {bRange[0]} ~ {bRange[1]}
                  </Typography>
                  <Slider value={bRange} min={0} max={imgWidth} onChange={(_, v) => setBRange(v)} valueLabelDisplay="auto" sx={{ color: 'error.main' }} />
                </Box>
                <Button variant="outlined" onClick={handleMeasure} disabled={loading || !lutInfo || !detectInfo}>
                  {loading ? '측정 중…' : 'A/B 단차 측정'}
                </Button>
                {measureResult?.step_diff_mm != null && (
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip size="small" color="success" label={`A: ${measureResult.height_a_mm} mm`} />
                    <Chip size="small" color="error" label={`B: ${measureResult.height_b_mm} mm`} />
                    <Chip size="small" color="primary" label={`단차: ${measureResult.step_diff_mm} mm`} />
                  </Stack>
                )}
              </Stack>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
              결과 이미지 (노란 점 = 검출된 레이저 선)
            </Typography>
            <Box
              sx={{
                width: '100%',
                minHeight: 320,
                bgcolor: '#000',
                borderRadius: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
              }}
            >
              {resultImage ? (
                <img src={resultImage} alt="result" style={{ maxWidth: '100%', maxHeight: '70vh', display: 'block' }} />
              ) : (
                <Typography variant="body2" color="grey.500">
                  "캡처 & 검출"을 누르면 결과가 표시됩니다
                </Typography>
              )}
            </Box>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
