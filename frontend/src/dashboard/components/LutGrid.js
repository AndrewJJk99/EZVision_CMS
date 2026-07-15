import * as React from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Slider from '@mui/material/Slider';
import Chip from '@mui/material/Chip';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import IconButton from '@mui/material/IconButton';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import Alert from '@mui/material/Alert';

import { buildLut, saveLut, listLuts, deleteLut } from '../../services/measurement.api';
import { useCmsWorkspace } from './cms/useCmsWorkspace';
import { formatLutLabel } from './cms/constants';
import CmsSetupCard from './cms/CmsSetupCard';
import ResultImageCard from './cms/ResultImageCard';
import LaserColorToggle from './cms/LaserColorToggle';

export default function LutGrid() {
  const ws = useCmsWorkspace();

  const [incrementMm, setIncrementMm] = React.useState(2.5);
  const [baseMm, setBaseMm] = React.useState(0);
  const [reverseOrder, setReverseOrder] = React.useState(false);
  const [frameCount, setFrameCount] = React.useState(1);
  const [edgeMarginPct, setEdgeMarginPct] = React.useState(12);
  const [trimPct, setTrimPct] = React.useState(12);
  const [lutName, setLutName] = React.useState('');
  const [lutTable, setLutTable] = React.useState(null);
  const [draftReady, setDraftReady] = React.useState(false);
  const [luts, setLuts] = React.useState([]);

  const refreshLuts = React.useCallback(async () => {
    try {
      const res = await listLuts();
      const items = (res?.luts || []).filter((l) => l.camera_id === ws.cameraIdBackend);
      setLuts(items);
    } catch (_e) {
      setLuts([]);
    }
  }, [ws.cameraIdBackend]);

  React.useEffect(() => {
    refreshLuts();
  }, [refreshLuts]);

  const handleGenerateLut = async () => {
    const name = lutName.trim();
    const res = await ws.run(
      () => buildLut(ws.cameraIdBackend, {
        increment_mm: incrementMm,
        base_mm: baseMm,
        reverse_order: reverseOrder,
        frame_count: frameCount,
        edge_margin_ratio: edgeMarginPct / 100,
        trim_ratio: trimPct / 100,
        lut_name: name || null,
        save: false,
      }),
      'LUT 생성 완료 (아직 저장되지 않음)',
    );
    if (res) {
      setLutTable(res.table || null);
      setDraftReady(Boolean(res.table?.length));
      ws.applyImages(res);
    }
  };

  const handleSaveLut = async () => {
    const name = lutName.trim();
    const res = await ws.run(
      () => saveLut(ws.cameraIdBackend, { lut_name: name || null }),
      name ? `LUT "${name}" 저장 완료` : 'LUT 저장 완료',
    );
    if (res?.saved) {
      setDraftReady(false);
      await refreshLuts();
    }
  };

  const handleDeleteLut = async (file, label) => {
    if (!file) return;
    const ok = window.confirm(`LUT를 삭제할까요?\n${label || file}\n(연결 이미지도 함께 삭제됩니다)`);
    if (!ok) return;
    const res = await ws.run(
      () => deleteLut(ws.cameraIdBackend, file),
      'LUT 삭제 완료',
    );
    if (res?.deleted) await refreshLuts();
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
            title="LUT"
            description={
              <>
                계단블록 캡처 → <b>강건 자동 레이저 검출</b> → LUT 생성 → 저장.
                색상·노이즈 임계값은 장면에서 자동 결정됩니다.
              </>
            }
            {...ws}
          />
        </Box>

        <Card sx={{ minWidth: 0, overflow: 'hidden', flexShrink: 0, maxHeight: '48vh', overflowY: 'auto' }}>
          <CardContent sx={{ minWidth: 0 }}>
            <Grid container spacing={2} columns={12} disableEqualOverflow sx={{ alignItems: 'center' }}>
              <Grid size={{ xs: 12, md: 5 }}>
                <Stack spacing={1} sx={{ height: '100%' }}>
                  <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                      1. 캡처 &amp; 검출
                    </Typography>
                    <LaserColorToggle value={ws.laserColor} onChange={ws.setLaserColor} disabled={ws.loading} />
                  </Stack>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ alignItems: 'center' }}>
                    <Button
                      variant="contained"
                      size="small"
                      onClick={() => ws.handleCaptureDetect(
                        '캡처 & 검출 완료 (LUT)',
                        {
                          detect_mode: 'lut',
                        },
                      )}
                      disabled={ws.loading || !ws.calibFile}
                    >
                      {ws.loading ? '처리 중…' : '캡처 & 검출'}
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => ws.handleRedetect({
                        detect_mode: 'lut',
                      })}
                      disabled={ws.loading || !ws.detectInfo}
                    >
                      재검출
                    </Button>
                    {ws.detectInfo?.coverage != null && (
                      <Chip
                        size="small"
                        color={ws.detectInfo.coverage > 0.5 ? 'success' : 'warning'}
                        label={`${(ws.detectInfo.coverage * 100).toFixed(0)}%`}
                      />
                    )}
                    {ws.detectInfo?.laser_quality?.mean_snr != null && (
                      <Chip size="small" variant="outlined" label={`SNR ${ws.detectInfo.laser_quality.mean_snr}`} />
                    )}
                    {ws.detectInfo?.laser_quality?.mean_width_px != null && (
                      <Chip size="small" variant="outlined" label={`폭 ${ws.detectInfo.laser_quality.mean_width_px}px`} />
                    )}
                  </Stack>
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
                    2. LUT 생성 / 저장
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ alignItems: 'center' }}>
                    <TextField
                      size="small"
                      label="LUT 이름"
                      placeholder="예: 계단_5단"
                      value={lutName}
                      onChange={(e) => setLutName(e.target.value)}
                      sx={{ width: 140 }}
                      inputProps={{ maxLength: 64 }}
                    />
                    <TextField
                      type="number"
                      size="small"
                      label="프레임"
                      value={frameCount}
                      onChange={(e) => setFrameCount(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
                      sx={{ width: 84 }}
                      inputProps={{ min: 1, max: 10 }}
                    />
                    <TextField
                      type="number"
                      size="small"
                      label="Δmm"
                      value={incrementMm}
                      onChange={(e) => setIncrementMm(Number(e.target.value))}
                      sx={{ width: 88 }}
                    />
                    <TextField
                      type="number"
                      size="small"
                      label="기준mm"
                      value={baseMm}
                      onChange={(e) => setBaseMm(Number(e.target.value))}
                      sx={{ width: 88 }}
                    />
                    <FormControlLabel
                      control={<Switch size="small" checked={reverseOrder} onChange={(e) => setReverseOrder(e.target.checked)} />}
                      label="순서반전"
                      sx={{ mr: 0 }}
                    />
                    <Box sx={{ width: 120, px: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">
                        경계제외 {edgeMarginPct}%
                      </Typography>
                      <Slider
                        size="small"
                        value={edgeMarginPct}
                        min={0}
                        max={30}
                        onChange={(_, v) => setEdgeMarginPct(v)}
                        valueLabelDisplay="auto"
                      />
                    </Box>
                    <Box sx={{ width: 120, px: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">
                        Trim {trimPct}%
                      </Typography>
                      <Slider
                        size="small"
                        value={trimPct}
                        min={0}
                        max={25}
                        onChange={(_, v) => setTrimPct(v)}
                        valueLabelDisplay="auto"
                      />
                    </Box>
                    <Button
                      variant="contained"
                      size="small"
                      onClick={handleGenerateLut}
                      disabled={ws.loading || !ws.detectInfo}
                    >
                      {ws.loading ? '생성 중…' : 'LUT 생성'}
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={handleSaveLut}
                      disabled={ws.loading || !draftReady}
                    >
                      LUT 저장
                    </Button>
                    {draftReady && (
                      <Chip size="small" color="warning" label="미저장 미리보기" />
                    )}
                  </Stack>
                </Stack>
              </Grid>
            </Grid>

            {lutTable && (
              <Box sx={{ maxHeight: 180, overflow: 'auto', mt: 1.5 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>단</TableCell>
                      <TableCell align="right">높이(mm)</TableCell>
                      <TableCell align="right">y(px)</TableCell>
                      <TableCell align="right">x(px)</TableCell>
                      <TableCell align="right">픽셀수</TableCell>
                      <TableCell align="right">std(px)</TableCell>
                      <TableCell align="right">coverage</TableCell>
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
                        <TableCell align="right">{r.std_px ?? '-'}</TableCell>
                        <TableCell align="right">{r.coverage != null ? `${(r.coverage * 100).toFixed(0)}%` : '-'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            )}

            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary', mb: 1 }}>
                3. LUT 관리
              </Typography>
              {!luts.length ? (
                <Alert severity="info" sx={{ py: 0.5 }}>저장된 LUT가 없습니다.</Alert>
              ) : (
                <Box sx={{ maxHeight: 200, overflow: 'auto' }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell>이름</TableCell>
                        <TableCell>단</TableCell>
                        <TableCell>Δmm</TableCell>
                        <TableCell>생성시각</TableCell>
                        <TableCell>이미지</TableCell>
                        <TableCell align="right">삭제</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {luts.map((l) => (
                        <TableRow key={l.file} hover>
                          <TableCell>{formatLutLabel(l)}</TableCell>
                          <TableCell>{l.step_count ?? '-'}</TableCell>
                          <TableCell>{l.increment_mm ?? '-'}</TableCell>
                          <TableCell>{l.created_at ?? '-'}</TableCell>
                          <TableCell>
                            {l.image_exists ? (
                              <Chip size="small" color="success" label="있음" />
                            ) : (
                              <Chip size="small" variant="outlined" label="없음" />
                            )}
                          </TableCell>
                          <TableCell align="right">
                            <IconButton
                              size="small"
                              color="error"
                              disabled={ws.loading}
                              onClick={() => handleDeleteLut(l.file, formatLutLabel(l))}
                              aria-label="delete lut"
                            >
                              <DeleteOutlineIcon fontSize="small" />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}
            </Box>
          </CardContent>
        </Card>

        <ResultImageCard
          resultImage={ws.resultImage}
          originalImage={ws.resultImageFull}
          crop={ws.resultCrop}
          fill
        />
      </Stack>
    </Box>
  );
}
