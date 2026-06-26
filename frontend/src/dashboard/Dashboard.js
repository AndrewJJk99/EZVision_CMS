import React from 'react';
import { alpha } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import CameraGrid from './components/CameraGrid';
import LutGrid from './components/LutGrid';
import MeasurementGrid from './components/MeasurementGrid';
import SettingsGrid from './components/SettingsGrid';
import SideMenu from './components/SideMenu/SideMenu';
import AppTheme from '../shared-theme/AppTheme';
import { CameraAppProvider } from './context/CameraAppContext';
import { PageNavProvider, PAGES, pageToPath, pathToPage } from './context/PageNavContext';

function readInitialPage() {
  if (typeof window === 'undefined') return 'calibration';
  return pathToPage(window.location.pathname);
}

export default function Dashboard() {
  const [menuOpen, setMenuOpen] = React.useState(true);
  const [page, setPage] = React.useState(readInitialPage);

  const goTo = React.useCallback((nextPage) => {
    const target = PAGES.includes(nextPage) ? nextPage : 'calibration';
    setPage(target);
    const path = pageToPath(target);
    if (window.location.pathname !== path) {
      window.history.replaceState(null, '', path);
    }
  }, []);

  return (
    <AppTheme>
      <CssBaseline enableColorScheme />
      <CameraAppProvider>
        <PageNavProvider page={page} goTo={goTo}>
          <Box sx={{ display: 'flex', minHeight: '100vh', width: '100%', overflowX: 'hidden' }}>
            <SideMenu open={menuOpen} onToggle={() => setMenuOpen(!menuOpen)} />
            <Box
              component="main"
              sx={(theme) => ({
                flexGrow: 1,
                minWidth: 0,
                backgroundColor: theme.vars
                  ? `rgba(${theme.vars.palette.background.defaultChannel} / 1)`
                  : alpha(theme.palette.background.default, 1),
                overflowX: 'hidden',
                overflowY: page === 'lut' || page === 'measurement' ? 'hidden' : 'auto',
                display: page === 'lut' || page === 'measurement' ? 'flex' : 'block',
                flexDirection: 'column',
                height: page === 'lut' || page === 'measurement' ? '100vh' : undefined,
                px: { xs: 1.5, md: 3 },
                pb: page === 'lut' || page === 'measurement' ? { xs: 1.5, md: 2 } : 5,
                pt: { xs: 1, md: 2 },
                boxSizing: 'border-box',
              })}
            >
              <Stack
                spacing={1}
                sx={{
                  alignItems: 'stretch',
                  minWidth: 0,
                  maxWidth: '100%',
                  boxSizing: 'border-box',
                  ...(page === 'lut' || page === 'measurement'
                    ? { flex: 1, minHeight: 0, overflow: 'hidden' }
                    : {}),
                }}
              >
                {page === 'settings' ? (
                  <SettingsGrid key="settings-page" />
                ) : page === 'lut' ? (
                  <LutGrid key="lut-page" />
                ) : page === 'measurement' ? (
                  <MeasurementGrid key="measurement-page" />
                ) : (
                  <CameraGrid key="calibration-page" />
                )}
              </Stack>
            </Box>
          </Box>
        </PageNavProvider>
      </CameraAppProvider>
    </AppTheme>
  );
}
