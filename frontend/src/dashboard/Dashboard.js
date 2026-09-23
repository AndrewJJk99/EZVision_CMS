import React from 'react';
import { alpha } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import SettingsGrid from './components/SettingsGrid';
import LaserPlaneGrid from './components/LaserPlaneGrid';
import SideMenu from './components/SideMenu/SideMenu';
import AppTheme from '../shared-theme/AppTheme';
import { CameraAppProvider } from './context/CameraAppContext';
import { PageNavProvider, PAGES, pageToPath, pathToPage } from './context/PageNavContext';

function readInitialPage() {
  if (typeof window === 'undefined') return 'cms';
  return pathToPage(window.location.pathname);
}

export default function Dashboard() {
  const [menuOpen, setMenuOpen] = React.useState(true);
  const [page, setPage] = React.useState(readInitialPage);

  const goTo = React.useCallback((nextPage) => {
    const target = PAGES.includes(nextPage) ? nextPage : 'cms';
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
                overflowY: 'auto',
                display: 'block',
                px: { xs: 1.5, md: 3 },
                pb: 5,
                pt: { xs: 1, md: 2 },
                boxSizing: 'border-box',
              })}
            >
              <Stack spacing={1} sx={{ alignItems: 'stretch', minWidth: 0, maxWidth: '100%', boxSizing: 'border-box' }}>
                {page === 'settings' ? (
                  <SettingsGrid key="settings-page" />
                ) : (
                  <LaserPlaneGrid key="cms-page" />
                )}
              </Stack>
            </Box>
          </Box>
        </PageNavProvider>
      </CameraAppProvider>
    </AppTheme>
  );
}
