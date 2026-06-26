import * as React from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';

import { useCameraApp } from '../../../../context/CameraAppContext';

export default function CameraMonitorControl({ onCameraStateChange }) {
  const { activeCameras } = useCameraApp();
  const [monitorCameras, setMonitorCameras] = React.useState(activeCameras);

  const notifyParent = React.useCallback(
    (next) => {
      const selectedCount = Object.values(next).filter(Boolean).length;
      window.dispatchEvent(
        new CustomEvent('monitorCountChanged', { detail: { count: selectedCount } }),
      );
      if (onCameraStateChange) {
        onCameraStateChange({
          1: { enabled: next[1] },
          2: { enabled: next[2] },
          3: { enabled: next[3] },
          4: { enabled: next[4] },
        });
      }
    },
    [onCameraStateChange],
  );

  React.useEffect(() => {
    setMonitorCameras(activeCameras);
    notifyParent(activeCameras);
  }, [activeCameras]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleMonitorCameraChange = (cameraNum) => (event) => {
    const next = { ...monitorCameras, [cameraNum]: event.target.checked };
    setMonitorCameras(next);
    notifyParent(next);
  };

  const activeCount = Object.values(monitorCameras).filter(Boolean).length;

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 1,
        py: 0.25,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
        <Typography component="span" variant="subtitle2" sx={{ fontWeight: 600 }}>
          Monitor
        </Typography>
        <FormGroup row sx={{ gap: 0.5, m: 0 }}>
          {[1, 2, 3, 4].map((num) => (
            <FormControlLabel
              key={num}
              value={String(num)}
              control={
                <Checkbox
                  size="small"
                  checked={monitorCameras[num]}
                  onChange={handleMonitorCameraChange(num)}
                />
              }
              label={String(num)}
              sx={{ mr: 1, '& .MuiFormControlLabel-label': { fontSize: '0.875rem' } }}
            />
          ))}
        </FormGroup>
      </Box>
      <Chip size="small" variant="outlined" label={`${activeCount}대 활성`} />
    </Box>
  );
}
