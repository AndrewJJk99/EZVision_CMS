import React from 'react';
import { BrowserRouter as Router, Route, Routes, Navigate } from 'react-router-dom';
import { alpha } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import CameraGrid from './components/CameraGrid';
import SettingsGrid from './components/SettingsGrid';
import SideMenu from './components/SideMenu/SideMenu';
import AppTheme from '../shared-theme/AppTheme';
import { CameraAppProvider } from './context/CameraAppContext';

export default function Dashboard() {
  const [menuOpen, setMenuOpen] = React.useState(true);

  return (
    <Router>
      <AppTheme>
        <CssBaseline enableColorScheme />
        <CameraAppProvider>
          <Box sx={{ display: 'flex' }}>
            <SideMenu open={menuOpen} onToggle={() => setMenuOpen(!menuOpen)} />
            <Box
              component="main"
              sx={(theme) => ({
                flexGrow: 1,
                backgroundColor: theme.vars
                  ? `rgba(${theme.vars.palette.background.defaultChannel} / 1)`
                  : alpha(theme.palette.background.default, 1),
                overflow: 'auto',
              })}
            >
              <Stack
                spacing={1}
                sx={{
                  alignItems: 'center',
                  mx: 3,
                  pb: 5,
                  mt: { xs: 8, md: 0 },
                  width: '100%',
                }}
              >
                <Routes>
                  <Route path="/" element={<Navigate to="/camera" replace />} />
                  <Route path="/camera" element={<CameraGrid />} />
                  <Route path="/settings" element={<SettingsGrid />} />
                </Routes>
              </Stack>
            </Box>
          </Box>
        </CameraAppProvider>
      </AppTheme>
    </Router>
  );
}
