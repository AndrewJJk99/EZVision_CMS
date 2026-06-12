import * as React from 'react';
import { styled } from '@mui/material/styles';
import NotificationsRoundedIcon from '@mui/icons-material/NotificationsRounded';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import MuiDrawer, { drawerClasses } from '@mui/material/Drawer';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import IconButton from '@mui/material/IconButton';
import { Typography } from '@mui/material';
import MenuContent from './MenuContent';
import MenuButton from './MenuButton';
import ColorModeIconDropdown from '../../../shared-theme/ColorModeIconDropdown';

const drawerWidth = 240;
const collapsedWidth = 64;

const openedMixin = (theme) => ({
  width: drawerWidth,
  transition: theme.transitions.create('width', {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.enteringScreen,
  }),
  overflowX: 'hidden',
});

const closedMixin = (theme) => ({
  transition: theme.transitions.create('width', {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  overflowX: 'hidden',
  width: collapsedWidth,
});

const Drawer = styled(MuiDrawer, { shouldForwardProp: (prop) => prop !== 'open' })(
  ({ theme, open }) => ({
    width: drawerWidth,
    flexShrink: 0,
    whiteSpace: 'nowrap',
    boxSizing: 'border-box',
    ...(open && {
      ...openedMixin(theme),
      [`& .${drawerClasses.paper}`]: openedMixin(theme),
    }),
    ...(!open && {
      ...closedMixin(theme),
      [`& .${drawerClasses.paper}`]: closedMixin(theme),
    }),
  }),
);

export default function SideMenu({ open = true, onToggle }) {
  return (
    <Drawer
      variant="permanent"
      open={open}
      sx={{
        display: { xs: 'none', md: 'block' },
        [`& .${drawerClasses.paper}`]: {
          backgroundColor: 'background.paper',
        },
      }}
    >
      <Box
        sx={{
          display: 'flex',
          p: 1,
          alignItems: 'center',
          justifyContent: open ? 'flex-start' : 'center',
          minHeight: 48,
          position: 'relative',
        }}
      >
        {!open && onToggle && (
          <IconButton
            onClick={onToggle}
            sx={{
              position: 'absolute',
              left: '50%',
              transform: 'translateX(-50%)',
            }}
            aria-label="open menu"
          >
            <ChevronRightIcon />
          </IconButton>
        )}
        {open && onToggle && (
          <IconButton
            onClick={onToggle}
            sx={{
              mr: 1,
              ml: -0.5,
            }}
            aria-label="close menu"
          >
            <ChevronLeftIcon />
          </IconButton>
        )}
        <Typography 
          variant="h6" 
          component="h6"
          sx={{
            opacity: open ? 1 : 0,
            transition: 'opacity 0.2s',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            width: open ? 'auto' : 0,
          }}
        >          
          EZVision CMS
        </Typography>
        
      </Box>
      <Divider />
      <MenuContent open={open} />
      <Stack
        direction="row"
        sx={{
          p: 1,
          gap: 1,
          alignItems: 'center',
          justifyContent: open ? 'flex-start' : 'center',
          borderTop: '1px solid',
          borderColor: 'divider',
        }}
      >
        <MenuButton >
          <NotificationsRoundedIcon />
        </MenuButton >
        <Box
          sx={{
            opacity: open ? 1 : 0,
            transition: 'opacity 0.2s',
            overflow: 'hidden',
            width: open ? 'auto' : 0,
          }}
        >
          <ColorModeIconDropdown />
        </Box>
      </Stack>

    </Drawer>
  );
}


