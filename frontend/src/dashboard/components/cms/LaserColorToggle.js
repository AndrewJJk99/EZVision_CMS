import * as React from 'react';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';

/**
 * 레이저 색(파랑/빨강) 전환 토글.
 * 값/변경 핸들러는 useCmsWorkspace의 laserColor / setLaserColor를 그대로 전달한다.
 */
export default function LaserColorToggle({ value, onChange, size = 'small', disabled = false }) {
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
        레이저 색
      </Typography>
      <ToggleButtonGroup
        exclusive
        size={size}
        value={value || 'blue'}
        onChange={(_e, v) => {
          if (v) onChange(v);
        }}
        disabled={disabled}
      >
        <ToggleButton value="blue" sx={{ px: 1.5, color: 'primary.main', '&.Mui-selected': { bgcolor: 'primary.main', color: '#fff', '&:hover': { bgcolor: 'primary.dark' } } }}>
          파랑
        </ToggleButton>
        <ToggleButton value="red" sx={{ px: 1.5, color: 'error.main', '&.Mui-selected': { bgcolor: 'error.main', color: '#fff', '&:hover': { bgcolor: 'error.dark' } } }}>
          빨강
        </ToggleButton>
      </ToggleButtonGroup>
    </Stack>
  );
}
