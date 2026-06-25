import React from 'react';
import { alpha } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import CameraGrid from './components/CameraGrid';
import CmsGrid from './components/CmsGrid';
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
          <Box sx={{ display: 'flex', minHeight: '100vh', width: '100%' }}>
            <SideMenu open={menuOpen} onToggle={() => setMenuOpen(!menuOpen)} />
            <Box
              component="main"
              sx={(theme) => ({
                flexGrow: 1,
                minWidth: 0,
                backgroundColor: theme.vars
                  ? `rgba(${theme.vars.palette.background.defaultChannel} / 1)`
                  : alpha(theme.palette.background.default, 1),
                overflow: 'auto',
              })}
            >
              <Stack
                spacing={1}
                sx={{
                  alignItems: 'stretch',
                  alignSelf: 'stretch',
                  mx: { xs: 1.5, md: 3 },
                  pb: 5,
                  pt: { xs: 1, md: 2 },
                  width: '100%',
                  maxWidth: '100%',
                  boxSizing: 'border-box',
                }}
              >
                {page === 'settings' ? (
                  <SettingsGrid key="settings-page" />
                ) : page === 'cms' ? (
                  <CmsGrid key="cms-page" />
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
