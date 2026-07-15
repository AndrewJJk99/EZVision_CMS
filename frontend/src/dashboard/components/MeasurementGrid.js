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
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';

import { listLuts, getLut, detectLaser, detectLutImage, measureStep, measureSteps, measureGap } from '../../services/measurement.api';
import { useCmsWorkspace } from './cms/useCmsWorkspace';
import { usePageNav } from '../context/PageNavContext';
import { formatLutLabel } from './cms/constants';
import CmsSetupCard from './cms/CmsSetupCard';
import ResultImageCard from './cms/ResultImageCard';
import RoiPickDialog from './cms/RoiPickDialog';
import LaserColorToggle from './cms/LaserColorToggle';

export default function MeasurementGrid() {
  const ws = useCmsWorkspace();
  const { page } = usePageNav();

  const [luts, setLuts] = React.useState([]);
  const [lutFile, setLutFile] = React.useState('');
  const [lutImageFile, setLutImageFile] = React.useState('');
  const [lutInfo, setLutInfo] = React.useState(null);
  const [reverseOrder] = React.useState(false);
  const [measurementTab, setMeasurementTab] = React.useState('flush');
  const [showAbMeasure, setShowAbMeasure] = React.useState(false);
  const [aRoi, setARoi] = React.useState(null);
  const [bRoi, setBRoi] = React.useState(null);
  const [measureResult, setMeasureResult] = React.useState(null);
  const [stepResult, setStepResult] = React.useState(null);
  const [gapResult, setGapResult] = React.useState(null);
  const [gapMmPerPx, setGapMmPerPx] = React.useState('');
  const [gapMinPx, setGapMinPx] = React.useState(2);
  const [gapMaxPx, setGapMaxPx] = React.useState(400);
  const [gapMinStepDy, setGapMinStepDy] = React.useState('');
  const [gapARoi, setGapARoi] = React.useState(null);
  const [gapBRoi, setGapBRoi] = React.useState(null);
  const [gapCaptured, setGapCaptured] = React.useState(false);
  // A/B ROI 확대 선택: { tab: 'flush'|'gap', key: 'a'|'b' } | null
  const [roiPick, setRoiPick] = React.useState(null);

  const refreshLuts = React.useCallback(async () => {
    try {
      const res = await listLuts();
      const items = res?.luts || [];
      setLuts(items);
      const forCamera = items.filter((l) => l.camera_id === ws.cameraIdBackend);
      if (forCamera.length) {
        setLutFile((prev) => (prev && forCamera.some((l) => l.file === prev) ? prev : forCamera[0].file));
      } else {
        setLutFile('');
        setLutInfo(null);
      }
    } catch (e) {
      setLuts([]);
      setLutFile('');
      setLutInfo(null);
    }
  }, [ws.cameraIdBackend]);

  const refreshLut = React.useCallback(async () => {
    if (!lutFile) {
      setLutInfo(null);
      return;
    }
    try {
      setLutInfo(await getLut(ws.cameraIdBackend, lutFile));
    } catch (e) {
      setLutInfo(null);
    }
  }, [ws.cameraIdBackend, lutFile]);

  React.useEffect(() => {
    if (page === 'measurement') refreshLuts();
  }, [page, refreshLuts]);

  React.useEffect(() => {
    refreshLut();
  }, [refreshLut]);

  React.useEffect(() => {
    if (page === 'measurement' && measurementTab === 'gap') {
      ws.refreshCalibrations?.();
    }
  }, [page, measurementTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedCalib = React.useMemo(
    () => (ws.calibrations || []).find((c) => c.file === ws.calibFile) || null,
    [ws.calibrations, ws.calibFile],
  );

  const calibPlaneScale = selectedCalib?.plane_scale || null;

  // 선택한 캘리브레이션의 plane_scale을 간격 mm/px에 자동 적용
  React.useEffect(() => {
    const mm = calibPlaneScale?.mm_per_px;
    if (mm != null && Number(mm) > 0) {
      setGapMmPerPx(String(mm));
    } else {
      setGapMmPerPx('');
    }
  }, [ws.calibFile, calibPlaneScale?.mm_per_px]);

  const lutsForCamera = React.useMemo(
    () => luts.filter((l) => l.camera_id === ws.cameraIdBackend),
    [luts, ws.cameraIdBackend],
  );

  React.useEffect(() => {
    if (lutInfo == null) return;
    setLutImageFile(lutInfo.image_file || '');
  }, [lutInfo]);

  const selectedLut = React.useMemo(
    () => lutsForCamera.find((l) => l.file === lutFile) || null,
    [lutsForCamera, lutFile],
  );

  const lutImagesForCamera = React.useMemo(
    () => lutsForCamera.filter((l) => l.image_file && l.image_exists),
    [lutsForCamera],
  );

  const handleMeasureAnalyze = async () => {
    setStepResult(null);
    setMeasureResult(null);

    const res = await ws.run(async () => {
      const cap = lutImageFile
        ? await detectLutImage(ws.cameraIdBackend, {
            lut_file: lutFile || null,
            image_file: lutImageFile,
            ...ws.detectionPayload(),
          })
        : await detectLaser(ws.cameraIdBackend, {
            calibration_file: ws.calibFile || null,
            use_stored: false,
            ...ws.detectionPayload(),
          });
      ws.applyCaptureResult(cap);

      const steps = await measureSteps(ws.cameraIdBackend, {
        reverse_order: reverseOrder,
        lut_file: lutFile || null,
      });
      return { cap, steps };
    }, '캡처 및 단차 분석 완료');

    if (res?.steps) {
      setStepResult(res.steps);
      ws.applyImages(res.steps);
    }
  };

  const handleMeasure = async () => {
    const res = await ws.run(
      () => measureStep(ws.cameraIdBackend, {
        a_roi: aRoi,
        b_roi: bRoi,
        lut_file: lutFile || null,
      }),
      'A/B 단차 측정 완료',
    );
    if (res) {
      setMeasureResult(res);
      ws.applyImages(res);
    }
  };

  const handleGapMeasure = async (forceRoi = false) => {
    setGapResult(null);
    const scale = parseFloat(gapMmPerPx);
    const mmPerPx = Number.isFinite(scale) && scale > 0 ? scale : null;

    const a = gapARoi;
    const b = gapBRoi;
    const useRoi = Boolean(forceRoi && a && b);
    if (forceRoi && (!a || !b)) return;

    const detectBase = {
      ...ws.detectionPayload(),
    };

    // 자동: 항상 새 캡처. A/B: 간격용 캡처가 있으면 그 프레임 재사용, 없으면 새 캡처.
    const useStored = Boolean(forceRoi && gapCaptured);

    const res = await ws.run(async () => {
      const payload = {
        ...detectBase,
        calibration_file: ws.calibFile || null,
        use_stored: useStored,
        redetect: true,
        mm_per_px: mmPerPx,
        use_saved_scale: true,
        min_gap_px: gapMinPx,
        max_gap_px: gapMaxPx,
      };
      const minStepDy = parseFloat(gapMinStepDy);
      if (!useRoi && Number.isFinite(minStepDy) && minStepDy > 0) {
        payload.min_step_dy_px = minStepDy;
      }
      if (useRoi) {
        payload.a_roi = { x0: a.x0, y0: a.y0, x1: a.x1, y1: a.y1 };
        payload.b_roi = { x0: b.x0, y0: b.y0, x1: b.x1, y1: b.y1 };
      }
      return measureGap(ws.cameraIdBackend, payload);
    }, useRoi ? 'A/B 간격 측정 완료' : '캡처 & 자동 간격 측정 완료');

    if (res) {
      setGapResult(res);
      ws.applyImages(res);
      if (res.mm_per_px != null) setGapMmPerPx(String(res.mm_per_px));
      setGapCaptured(true);
    }
  };

  const handleGapCaptureOnly = async () => {
    setGapResult(null);
    setGapARoi(null);
    setGapBRoi(null);
    setRoiPick(null);
    const detectBase = {
      ...ws.detectionPayload(),
    };
    const res = await ws.run(
      () => detectLaser(ws.cameraIdBackend, {
        calibration_file: ws.calibFile || null,
        use_stored: false,
        detect_mode: 'gap',
        ...detectBase,
      }),
      '간격용 이미지 캡처 완료',
    );
    if (res) {
      ws.applyCaptureResult(res);
      setGapCaptured(true);
    }
  };

  const handleGapAbMeasure = async () => {
    if (!gapARoi || !gapBRoi) return;
    await handleGapMeasure(true);
  };

  return (
    <Box
      sx={{
        width: '100%',
        maxWidth: '100%',
        minWidth: 0,
        minHeight: 0,
        flex: 1,
        overflow: 'hidden',
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Stack spacing={1.5} sx={{ minWidth: 0, maxWidth: '100%', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <Box
          sx={{
            flexShrink: 0,
            borderBottom: 1,
            borderColor: 'divider',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 1,
            pr: 1,
          }}
        >
          <Tabs
            value={measurementTab}
            onChange={(_, value) => {
              setMeasurementTab(value);
              setRoiPick(null);
              if (value === 'gap') {
                setGapCaptured(false);
                setGapResult(null);
              }
            }}
            sx={{ minHeight: 40 }}
          >
            <Tab value="flush" label="단차" sx={{ minHeight: 40, fontWeight: 600 }} />
            <Tab value="gap" label="간격" sx={{ minHeight: 40, fontWeight: 600 }} />
          </Tabs>
          <LaserColorToggle value={ws.laserColor} onChange={ws.setLaserColor} disabled={ws.loading} />
        </Box>

        <Box sx={{ flexShrink: 0 }}>
          <CmsSetupCard
            title={measurementTab === 'gap' ? '간격 측정' : '단차 측정'}
            description={
              measurementTab === 'gap' ? (
                <>
                  캘리브레이션에 저장된 <b>작업거리 mm/px</b>로 간격을 mm 환산합니다.
                  간격은 단차와 별도로 이미지를 캡처해 측정합니다.
                </>
              ) : (
                <>
                  LUT를 선택한 뒤 <b>측정</b>으로 캡처·레이저 검출·단차 분석을 진행합니다.
                  파란 레이저 선과 노이즈는 강건 자동 검출기가 구분합니다.
                </>
              )
            }
            {...ws}
          />
        </Box>

        <Card sx={{ minWidth: 0, flexShrink: 0, maxHeight: '42vh', overflowY: 'auto' }}>
          <CardContent sx={{ minWidth: 0 }}>
            {measurementTab === 'flush' && (
              <>
                <Grid container spacing={2} columns={12} disableEqualOverflow sx={{ alignItems: 'flex-start' }}>
                  <Grid size={{ xs: 12, md: 5 }}>
                    <Stack spacing={1}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                        1. LUT 선택
                      </Typography>
                      <TextField
                        select
                        fullWidth
                        size="small"
                        label="LUT 결과"
                        value={lutFile}
                        onChange={(e) => setLutFile(e.target.value)}
                        SelectProps={{
                          renderValue: (file) => {
                            const item = lutsForCamera.find((l) => l.file === file);
                            return item ? formatLutLabel(item) : file;
                          },
                        }}
                        helperText={
                          lutsForCamera.length
                            ? '측정에 사용할 LUT 선택'
                            : '저장된 LUT 없음 — LUT 탭에서 먼저 생성'
                        }
                      >
                        {lutsForCamera.map((l) => (
                          <MenuItem key={l.file} value={l.file}>
                            {formatLutLabel(l)}
                          </MenuItem>
                        ))}
                      </TextField>
                      {!lutFile && (
                        <Alert severity="warning" sx={{ py: 0.5 }}>
                          사용할 LUT를 선택하세요.
                        </Alert>
                      )}
                      {lutInfo && (
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          {(lutInfo.lut_name || selectedLut?.lut_name) && (
                            <Chip
                              size="small"
                              label={lutInfo.lut_name || selectedLut.lut_name}
                              color="primary"
                              variant="outlined"
                            />
                          )}
                          <Chip size="small" label={`${lutInfo.step_count ?? '-'}단`} />
                          {lutInfo.increment_mm != null && (
                            <Chip size="small" label={`Δ${lutInfo.increment_mm}mm`} />
                          )}
                        </Stack>
                      )}
                      <TextField
                        select
                        fullWidth
                        size="small"
                        label="저장 이미지"
                        value={lutImageFile}
                        onChange={(e) => setLutImageFile(e.target.value)}
                        helperText={
                          lutImagesForCamera.length
                            ? '선택 시 카메라 캡처 없이 저장 이미지로 빠르게 확인'
                            : '저장된 LUT 이미지 없음 — LUT를 다시 생성하면 함께 저장됩니다'
                        }
                      >
                        <MenuItem value="">사용 안 함 (카메라 캡처)</MenuItem>
                        {lutImagesForCamera.map((l) => (
                          <MenuItem key={`${l.file}:${l.image_file}`} value={l.image_file}>
                            {`${l.lut_name || l.file} | ${l.image_file}`}
                          </MenuItem>
                        ))}
                      </TextField>
                    </Stack>
                  </Grid>

                  <Grid
                    size={{ xs: 12, md: 7 }}
                    sx={{
                      borderLeft: { md: 1 },
                      borderColor: { md: 'divider' },
                      pl: { md: 2 },
                    }}
                  >
                    <Stack spacing={1}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                        2. 측정 실행
                      </Typography>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ alignItems: 'center' }}>
                        <Button
                          variant="contained"
                          size="small"
                          onClick={handleMeasureAnalyze}
                          disabled={ws.loading || !ws.calibFile || !lutFile}
                        >
                          {ws.loading ? '처리 중…' : '측정 (캡처 & 단차 분석)'}
                        </Button>
                        {stepResult?.steps && (
                          <Chip size="small" color="success" label={`검출된 단: ${stepResult.steps.length}`} />
                        )}
                        {ws.detectInfo?.coverage != null && !stepResult?.steps && (
                          <Chip size="small" label={`검출 ${ws.detectInfo.valid_columns}/${ws.detectInfo.total_columns}`} />
                        )}
                      </Stack>
                    </Stack>
                  </Grid>
                </Grid>

                {stepResult?.steps && (
                  <Box sx={{ maxHeight: 180, overflow: 'auto', mt: 1.5 }}>
                    <Table size="small" stickyHeader>
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

                <FormControlLabel
                  sx={{ mt: 1, mb: 0 }}
                  control={
                    <Checkbox
                      size="small"
                      checked={showAbMeasure}
                      onChange={(e) => {
                        setShowAbMeasure(e.target.checked);
                        if (!e.target.checked) {
                          setMeasureResult(null);
                        }
                      }}
                    />
                  }
                  label="A/B ROI 단차"
                />

                {showAbMeasure && (
                  <Stack spacing={1} sx={{ pl: 0.5, mt: 0.5 }}>
                    <Typography variant="caption" color="text.secondary">
                      A·B를 누르면 이미지가 확대됩니다. 박스를 그린 뒤 확인하세요.
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ alignItems: 'center' }}>
                      <Button
                        variant={aRoi ? 'contained' : 'outlined'}
                        color="success"
                        size="small"
                        onClick={() => setRoiPick({ tab: 'flush', key: 'a' })}
                        disabled={!ws.resultImage}
                      >
                        A 영역 선택
                      </Button>
                      <Button
                        variant={bRoi ? 'contained' : 'outlined'}
                        color="error"
                        size="small"
                        onClick={() => setRoiPick({ tab: 'flush', key: 'b' })}
                        disabled={!ws.resultImage}
                      >
                        B 영역 선택
                      </Button>
                      {aRoi && (
                        <Typography variant="caption" color="success.main">
                          A ({aRoi.x0},{aRoi.y0})–({aRoi.x1},{aRoi.y1})
                        </Typography>
                      )}
                      {bRoi && (
                        <Typography variant="caption" color="error.main">
                          B ({bRoi.x0},{bRoi.y0})–({bRoi.x1},{bRoi.y1})
                        </Typography>
                      )}
                      <Button
                        variant="outlined"
                        size="small"
                        onClick={handleMeasure}
                        disabled={ws.loading || !lutFile || !ws.detectInfo || !aRoi || !bRoi}
                      >
                        {ws.loading ? '측정 중…' : 'A/B 단차 측정'}
                      </Button>
                      {(aRoi || bRoi) && (
                        <Button
                          variant="text"
                          size="small"
                          onClick={() => {
                            setARoi(null);
                            setBRoi(null);
                            setMeasureResult(null);
                            setRoiPick(null);
                          }}
                        >
                          ROI 초기화
                        </Button>
                      )}
                      {measureResult?.step_diff_mm != null && (
                        <>
                          <Chip size="small" color="success" label={`A: ${measureResult.height_a_mm} mm`} />
                          <Chip size="small" color="error" label={`B: ${measureResult.height_b_mm} mm`} />
                          <Chip size="small" color="primary" label={`단차: ${measureResult.step_diff_mm} mm`} />
                        </>
                      )}
                    </Stack>
                  </Stack>
                )}
              </>
            )}

            {measurementTab === 'gap' && (
              <Stack spacing={2}>
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                    1. 자동 간격 측정
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    새 프레임을 캡처한 뒤 레이저 끊김(끝점) 사이 거리를 자동으로 찾습니다.
                    {calibPlaneScale?.mm_per_px != null
                      ? ` · 스케일 ${calibPlaneScale.mm_per_px} mm/px`
                      : ''}
                  </Typography>
                  <Grid container spacing={1.5} columns={12} disableEqualOverflow alignItems="center">
                    <Grid size={{ xs: 12, sm: 4, md: 3 }}>
                      <TextField
                        label="mm / px"
                        size="small"
                        fullWidth
                        value={gapMmPerPx}
                        onChange={(e) => setGapMmPerPx(e.target.value)}
                        placeholder="캘리브에서 자동"
                        helperText="비우면 캘리브 plane_scale 사용"
                      />
                    </Grid>
                    <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                      <TextField
                        label="최소 gap (px)"
                        size="small"
                        type="number"
                        fullWidth
                        value={gapMinPx}
                        onChange={(e) => setGapMinPx(Number(e.target.value) || 2)}
                      />
                    </Grid>
                    <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                      <TextField
                        label="최대 gap (px)"
                        size="small"
                        type="number"
                        fullWidth
                        value={gapMaxPx}
                        onChange={(e) => setGapMaxPx(Number(e.target.value) || 400)}
                      />
                    </Grid>
                    <Grid size={{ xs: 6, sm: 4, md: 2 }}>
                      <TextField
                        label="최소 단차 Δy (px)"
                        size="small"
                        type="number"
                        fullWidth
                        value={gapMinStepDy}
                        onChange={(e) => setGapMinStepDy(e.target.value)}
                        placeholder="자동"
                        helperText="비우면 단차 우선만"
                      />
                    </Grid>
                    <Grid size={{ xs: 12, md: 3 }}>
                      <Button
                        variant="contained"
                        onClick={() => handleGapMeasure(false)}
                        disabled={ws.loading || !ws.calibFile}
                        fullWidth
                      >
                        {ws.loading ? '측정 중…' : '캡처 & 자동 간격 측정'}
                      </Button>
                    </Grid>
                  </Grid>
                </Box>

                <Box sx={{ pt: 0.5, borderTop: 1, borderColor: 'divider' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                    2. A/B 영역으로 지정
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    간격용 캡처 후 A·B를 누르면 이미지가 확대됩니다. 박스를 그린 뒤 확인하세요.
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ alignItems: 'center' }}>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={handleGapCaptureOnly}
                      disabled={ws.loading || !ws.calibFile}
                    >
                      간격용 캡처
                    </Button>
                    <Button
                      variant={gapARoi ? 'contained' : 'outlined'}
                      color="success"
                      size="small"
                      onClick={() => setRoiPick({ tab: 'gap', key: 'a' })}
                      disabled={!ws.resultImage || !gapCaptured}
                    >
                      A 선택
                    </Button>
                    <Button
                      variant={gapBRoi ? 'contained' : 'outlined'}
                      color="error"
                      size="small"
                      onClick={() => setRoiPick({ tab: 'gap', key: 'b' })}
                      disabled={!ws.resultImage || !gapCaptured}
                    >
                      B 선택
                    </Button>
                    <Button
                      variant="contained"
                      color="secondary"
                      size="small"
                      onClick={handleGapAbMeasure}
                      disabled={ws.loading || !gapARoi || !gapBRoi}
                    >
                      {ws.loading ? '측정 중…' : 'A/B 간격 측정'}
                    </Button>
                    {(gapARoi || gapBRoi) && (
                      <Button
                        variant="text"
                        size="small"
                        onClick={() => {
                          setGapARoi(null);
                          setGapBRoi(null);
                          setRoiPick(null);
                        }}
                      >
                        ROI 초기화
                      </Button>
                    )}
                  </Stack>
                  {(gapARoi || gapBRoi) && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                      {gapARoi ? `A (${gapARoi.x0},${gapARoi.y0})–(${gapARoi.x1},${gapARoi.y1})` : 'A 미선택'}
                      {' · '}
                      {gapBRoi ? `B (${gapBRoi.x0},${gapBRoi.y0})–(${gapBRoi.x1},${gapBRoi.y1})` : 'B 미선택'}
                    </Typography>
                  )}
                </Box>

                {gapResult && (
                  <Box
                    sx={{
                      p: 1.5,
                      borderRadius: 1,
                      bgcolor: 'action.hover',
                      border: 1,
                      borderColor: 'divider',
                    }}
                  >
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                      측정 결과
                      {gapResult.mode === 'roi' ? ' (A/B)' : ' (자동)'}
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
                      {gapResult.gap_bright_mm != null
                        ? `${gapResult.gap_bright_mm} mm`
                        : gapResult.gap_bright_px != null
                          ? `${gapResult.gap_bright_px} px`
                          : gapResult.gap_mm != null
                            ? `${gapResult.gap_mm} mm`
                            : gapResult.gap_px != null
                              ? `${gapResult.gap_px} px`
                              : '—'}
                      {gapResult.gap_bright_px != null && (
                        <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                          (밝은코어 {gapResult.gap_bright_px} px
                          {gapResult.mm_per_px != null ? ` × ${gapResult.mm_per_px}` : ''})
                        </Typography>
                      )}
                    </Typography>
                    {gapResult.gap_px != null && gapResult.gap_bright_px != null && (
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                        레이저 끝(raw) 기준: {gapResult.gap_mm != null ? `${gapResult.gap_mm} mm ` : ''}({gapResult.gap_px} px)
                      </Typography>
                    )}
                    {gapResult?.left_end && gapResult?.right_end && (
                      <Typography variant="caption" color="text.secondary" display="block">
                        L ({gapResult.left_end.x}, {gapResult.left_end.y}) → R ({gapResult.right_end.x}, {gapResult.right_end.y})
                        {gapResult.step_dy_px != null ? `  · 단차 Δy ${gapResult.step_dy_px}px` : ''}
                        {gapResult.left_segment?.label && gapResult.right_segment?.label
                          ? `  · ${gapResult.left_segment.label}↔${gapResult.right_segment.label}`
                          : ''}
                      </Typography>
                    )}
                  </Box>
                )}
              </Stack>
            )}
          </CardContent>
        </Card>

        <ResultImageCard
          resultImage={ws.resultImage}
          originalImage={ws.resultImageFull}
          crop={ws.resultCrop}
          fill
          emptyHint="측정 실행 후 결과가 표시됩니다"
          roiSelection={{
            // A/B는 확대 다이얼로그에서 선택. 여기선 확정 ROI만 표시.
            enabled: false,
            active: null,
            rois: measurementTab === 'gap'
              ? { a: gapARoi, b: gapBRoi }
              : showAbMeasure
                ? { a: aRoi, b: bRoi }
                : { a: null, b: null },
            onChange: () => {},
          }}
        />

        <RoiPickDialog
          open={Boolean(roiPick)}
          label={(roiPick?.key || 'a').toUpperCase()}
          imageSrc={ws.resultImageFull || ws.resultImage}
          initialRoi={
            roiPick?.tab === 'gap'
              ? (roiPick.key === 'a' ? gapARoi : gapBRoi)
              : (roiPick?.key === 'a' ? aRoi : bRoi)
          }
          onClose={() => setRoiPick(null)}
          onConfirm={(roi) => {
            if (roiPick?.tab === 'gap') {
              if (roiPick.key === 'a') setGapARoi(roi);
              if (roiPick.key === 'b') setGapBRoi(roi);
              setGapResult(null);
            } else {
              if (roiPick?.key === 'a') setARoi(roi);
              if (roiPick?.key === 'b') setBRoi(roi);
              setMeasureResult(null);
            }
            setRoiPick(null);
          }}
        />
      </Stack>
    </Box>
  );
}
