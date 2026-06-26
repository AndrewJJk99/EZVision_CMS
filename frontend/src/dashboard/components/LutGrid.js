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

import { buildLut } from '../../services/measurement.api';
import { useCmsWorkspace } from './cms/useCmsWorkspace';
import CmsSetupCard from './cms/CmsSetupCard';
import ResultImageCard from './cms/ResultImageCard';

export default function LutGrid() {
  const ws = useCmsWorkspace();

  const [incrementMm, setIncrementMm] = React.useState(2.5);
  const [baseMm, setBaseMm] = React.useState(0);
  const [reverseOrder, setReverseOrder] = React.useState(false);
  const [stepSensitivity, setStepSensitivity] = React.useState(50);
  const [lutName, setLutName] = React.useState('');
  const [lutTable, setLutTable] = React.useState(null);

  const handleBuildLut = async () => {
    const name = lutName.trim();
    const res = await ws.run(
      () => buildLut(ws.cameraIdBackend, {
        increment_mm: incrementMm,
        base_mm: baseMm,
        reverse_order: reverseOrder,
        sensitivity: stepSensitivity,
        lut_name: name || null,
      }),
      name ? `LUT "${name}" 저장 완료` : 'LUT 생성 및 저장 완료',
    );
    if (res) {
      setLutTable(res.table || null);
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
            title="LUT"
            laserInDialog
          description={
            <>
              계단블록 캡처 → 레이저 검출 → LUT 저장. 검출 시 <b>가장 긴 선 하나만</b> 사용합니다.
              레이저 튜닝은 &quot;레이저 검출 설정&quot; 버튼에서 하세요.
            </>
          }
          {...ws}
          />
        </Box>

        <Card sx={{ minWidth: 0, overflow: 'hidden', flexShrink: 0 }}>
          <CardContent sx={{ minWidth: 0 }}>
            <Grid container spacing={2} columns={12} disableEqualOverflow sx={{ alignItems: 'center' }}>
              <Grid size={{ xs: 12, md: 5 }}>
                <Stack spacing={1} sx={{ height: '100%' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                    1. 캡처 &amp; 검출
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ alignItems: 'center' }}>
                    <Button variant="contained" size="small" onClick={() => ws.handleCaptureDetect()} disabled={ws.loading || !ws.calibFile}>
                      {ws.loading ? '처리 중…' : '캡처 & 검출'}
                    </Button>
                    <Button variant="outlined" size="small" onClick={ws.handleRedetect} disabled={ws.loading || !ws.detectInfo}>
                      재검출
                    </Button>
                    {ws.detectInfo?.coverage != null && (
                      <Chip
                        size="small"
                        color={ws.detectInfo.coverage > 0.5 ? 'success' : 'warning'}
                        label={`${(ws.detectInfo.coverage * 100).toFixed(0)}%`}
                      />
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
                    2. LUT 생성/저장
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
                        민감도 {stepSensitivity}
                      </Typography>
                      <Slider
                        size="small"
                        value={stepSensitivity}
                        min={0}
                        max={100}
                        onChange={(_, v) => setStepSensitivity(v)}
                        valueLabelDisplay="auto"
                      />
                    </Box>
                    <Button variant="contained" size="small" onClick={handleBuildLut} disabled={ws.loading || !ws.detectInfo}>
                      {ws.loading ? '생성 중…' : 'LUT 저장'}
                    </Button>
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
          </CardContent>
        </Card>

        <ResultImageCard resultImage={ws.resultImage} fill />
      </Stack>
    </Box>
  );
}
