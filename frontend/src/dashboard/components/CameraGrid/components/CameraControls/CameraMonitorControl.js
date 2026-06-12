import * as React from 'react';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Grid from '@mui/material/Grid2';
import Typography from '@mui/material/Typography';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';

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

  return (
    <Card sx={{ height: '100%' }}>
      <Grid container spacing={1} columns={12}>
        <Grid size={{ xs: 12 }}>
          <CardContent>
            <Typography component="h2" variant="subtitle2" gutterBottom sx={{ fontWeight: '600' }}>
              Monitor
            </Typography>
            <FormGroup row>
              {[1, 2, 3, 4].map((num) => (
                <FormControlLabel
                  key={num}
                  value={String(num)}
                  control={
                    <Checkbox
                      checked={monitorCameras[num]}
                      onChange={handleMonitorCameraChange(num)}
                    />
                  }
                  label={String(num)}
                />
              ))}
            </FormGroup>
          </CardContent>
        </Grid>
      </Grid>
    </Card>
  );
}
