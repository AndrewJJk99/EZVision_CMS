import * as React from 'react';
import Box from '@mui/material/Box';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Slider from '@mui/material/Slider';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';

function sliderRow(label, value, setter, min, max, step = 1) {
  return (
    <Grid size={{ xs: 12, sm: 6 }} key={label}>
      <Typography variant="body2" gutterBottom>
        {label}: {value}
      </Typography>
      <Slider value={value} min={min} max={max} step={step} onChange={(_, v) => setter(v)} size="small" />
    </Grid>
  );
}

export default function LaserDetectSettings({
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
}) {
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          검출 방식
        </Typography>
        <TextField select size="small" value={method} onChange={(e) => setMethod(e.target.value)} sx={{ minWidth: 220 }}>
          <MenuItem value="auto">자동(밝은 곳 찾기) — 추천</MenuItem>
          <MenuItem value="hsv">색상(파란색 HSV) — 수동</MenuItem>
        </TextField>
      </Stack>

      {method === 'auto' ? (
        <Grid container spacing={2} columns={12} disableEqualOverflow>
          {sliderRow('민감도 보정(±)', threshOffset, setThreshOffset, -60, 60)}
          {sliderRow('선 잇기 간격(px)', bridgeGap, setBridgeGap, 1, 200)}
          <Grid size={{ xs: 12, sm: 6 }}>
            <FormControlLabel control={<Switch checked={blueBoost} onChange={(e) => setBlueBoost(e.target.checked)} />} label="파란색 우선" />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <FormControlLabel control={<Switch checked={roiEnabled} onChange={(e) => setRoiEnabled(e.target.checked)} />} label="ROI 밴드 사용" />
          </Grid>
        </Grid>
      ) : (
        <Grid container spacing={2} columns={12} disableEqualOverflow>
          {sliderRow('H low', hLow, setHLow, 0, 179)}
          {sliderRow('H high', hHigh, setHHigh, 0, 179)}
          {sliderRow('S min', sMin, setSMin, 0, 255)}
          {sliderRow('V min', vMin, setVMin, 0, 255)}
          {sliderRow('선 잇기 간격(px)', bridgeGap, setBridgeGap, 1, 200)}
          <Grid size={{ xs: 12, sm: 6 }}>
            <FormControlLabel control={<Switch checked={roiEnabled} onChange={(e) => setRoiEnabled(e.target.checked)} />} label="ROI 밴드 사용" />
          </Grid>
        </Grid>
      )}

      {roiEnabled && (
        <Box>
          <Typography variant="body2" gutterBottom>
            레이저가 지나는 세로 구간 Y: {roiY[0]} ~ {roiY[1]}
          </Typography>
          <Slider value={roiY} min={0} max={imgHeight} onChange={(_, v) => setRoiY(v)} valueLabelDisplay="auto" sx={{ color: 'secondary.main' }} />
        </Box>
      )}
    </Stack>
  );
}
