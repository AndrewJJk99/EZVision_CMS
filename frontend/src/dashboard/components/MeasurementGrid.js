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
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';

import { listLuts, getLut, detectLaser, measureStep, measureSteps } from '../../services/measurement.api';
import { useCmsWorkspace } from './cms/useCmsWorkspace';
import { usePageNav } from '../context/PageNavContext';
import { formatLutLabel } from './cms/constants';
import CmsSetupCard from './cms/CmsSetupCard';
import ResultImageCard from './cms/ResultImageCard';

export default function MeasurementGrid() {
  const ws = useCmsWorkspace();
  const { page } = usePageNav();

  const [luts, setLuts] = React.useState([]);
  const [lutFile, setLutFile] = React.useState('');
  const [lutInfo, setLutInfo] = React.useState(null);
  const [stepSensitivity, setStepSensitivity] = React.useState(50);
  const [reverseOrder] = React.useState(false);
  const [showAbMeasure, setShowAbMeasure] = React.useState(false);
  const [aRange, setARange] = React.useState([100, 300]);
  const [bRange, setBRange] = React.useState([900, 1100]);
  const [measureResult, setMeasureResult] = React.useState(null);
  const [stepResult, setStepResult] = React.useState(null);

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

  const lutsForCamera = React.useMemo(
    () => luts.filter((l) => l.camera_id === ws.cameraIdBackend),
    [luts, ws.cameraIdBackend],
  );

  React.useEffect(() => {
    if (lutInfo == null) return;
    setStepSensitivity(lutInfo.sensitivity != null ? lutInfo.sensitivity : 50);
  }, [lutInfo]);

  const selectedLut = React.useMemo(
    () => lutsForCamera.find((l) => l.file === lutFile) || null,
    [lutsForCamera, lutFile],
  );

  const handleMeasureAnalyze = async () => {
    setStepResult(null);
    setMeasureResult(null);

    const res = await ws.run(async () => {
      const cap = await detectLaser(ws.cameraIdBackend, {
        calibration_file: ws.calibFile || null,
        use_stored: false,
        ...ws.detectionPayload(),
      });
      ws.applyCaptureResult(cap);

      const steps = await measureSteps(ws.cameraIdBackend, {
        reverse_order: reverseOrder,
        sensitivity: stepSensitivity,
        lut_file: lutFile || null,
      });
      return { cap, steps };
    }, '캡처 및 단차 분석 완료');

    if (res?.steps) {
      setStepResult(res.steps);
      if (res.steps.image) ws.setResultImage(res.steps.image);
    }
  };

  const handleMeasure = async () => {
    const res = await ws.run(
      () => measureStep(ws.cameraIdBackend, {
        a_x0: aRange[0],
        a_x1: aRange[1],
        b_x0: bRange[0],
        b_x1: bRange[1],
        lut_file: lutFile || null,
      }),
      'A/B 단차 측정 완료',
    );
    if (res) {
      setMeasureResult(res);
      if (res.image) ws.setResultImage(res.image);
    }
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
        <Box sx={{ flexShrink: 0 }}>
          <CmsSetupCard
            title="측정"
            laserInDialog
          description={
            <>
              LUT를 선택한 뒤 <b>측정</b> 버튼 한 번으로 캡처·레이저 검출·단차 분석까지 진행합니다.
              레이저 튜닝은 &quot;레이저 검출 설정&quot; 버튼에서 하세요. (카메라·레이저 위치 고정 필수)
            </>
          }
          {...ws}
          />
        </Box>

        <Card sx={{ minWidth: 0, flexShrink: 0, maxHeight: '42vh', overflowY: 'auto' }}>
          <CardContent sx={{ minWidth: 0 }}>
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
                    <Box sx={{ width: 140, px: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">
                        민감도 {stepSensitivity}
                        {lutInfo?.sensitivity != null ? '' : ' (기본)'}
                      </Typography>
                      <Slider
                        size="small"
                        value={stepSensitivity}
                        min={0}
                        max={100}
                        onChange={(_, v) => setStepSensitivity(v)}
                        valueLabelDisplay="auto"
                        disabled={!lutFile}
                      />
                    </Box>
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
                    if (!e.target.checked) setMeasureResult(null);
                  }}
                />
              }
              label="A/B 두 구간 단차"
            />

            {showAbMeasure && (
              <Stack spacing={1} sx={{ pl: 0.5, mt: 0.5 }}>
                <Typography variant="caption" color="text.secondary">
                  이미 캡처된 이미지에서 A·B 구간 X 범위를 지정해 두 영역의 단차를 측정합니다.
                </Typography>
                <Grid container spacing={2} columns={12} disableEqualOverflow>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="caption" gutterBottom display="block">
                      A 구간 X: {aRange[0]} ~ {aRange[1]}
                    </Typography>
                    <Slider
                      size="small"
                      value={aRange}
                      min={0}
                      max={ws.imgWidth}
                      onChange={(_, v) => setARange(v)}
                      valueLabelDisplay="auto"
                      sx={{ color: 'success.main', maxWidth: '100%' }}
                    />
                  </Grid>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="caption" gutterBottom display="block">
                      B 구간 X: {bRange[0]} ~ {bRange[1]}
                    </Typography>
                    <Slider
                      size="small"
                      value={bRange}
                      min={0}
                      max={ws.imgWidth}
                      onChange={(_, v) => setBRange(v)}
                      valueLabelDisplay="auto"
                      sx={{ color: 'error.main', maxWidth: '100%' }}
                    />
                  </Grid>
                </Grid>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ alignItems: 'center' }}>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={handleMeasure}
                    disabled={ws.loading || !lutFile || !ws.detectInfo}
                  >
                    {ws.loading ? '측정 중…' : 'A/B 단차 측정'}
                  </Button>
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
          </CardContent>
        </Card>

        <ResultImageCard resultImage={ws.resultImage} fill emptyHint="측정 실행 후 결과가 표시됩니다" />
      </Stack>
    </Box>
  );
}
