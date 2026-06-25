import * as React from 'react';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import CameraIcon from '@mui/icons-material/Camera';
import StraightenIcon from '@mui/icons-material/Straighten';
import SettingsRoundedIcon from '@mui/icons-material/SettingsRounded';
import { usePageNav } from '../../context/PageNavContext';

const mainListItems = [
  { text: 'Calibration', icon: <CameraIcon />, page: 'calibration' },
  { text: 'CMS', icon: <StraightenIcon />, page: 'cms' },
  { text: 'Settings', icon: <SettingsRoundedIcon />, page: 'settings' },
];

export default function MenuContent({ open = true }) {
  const { page, goTo } = usePageNav();

  return (
    <Stack sx={{ flexGrow: 1, p: 0.5 }}>
      <List dense>
        {mainListItems.map((item) => (
          <ListItem key={item.page} disablePadding sx={{ display: 'block' }}>
            <ListItemButton
              selected={page === item.page}
              onClick={() => goTo(item.page)}
              sx={{
                justifyContent: open ? 'flex-start' : 'center',
                minHeight: 36,
                py: 0.5,
                px: open ? 1.5 : 0.5,
                '&.Mui-selected': {
                  backgroundColor: 'rgba(0, 0, 0, 0.08)',
                },
              }}
            >
              <ListItemIcon
                sx={{
                  minWidth: open ? 36 : 0,
                  justifyContent: 'center',
                }}
              >
                {item.icon}
              </ListItemIcon>
              <ListItemText
                primary={item.text}
                sx={{
                  opacity: open ? 1 : 0,
                  transition: 'opacity 0.2s',
                }}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Stack>
  );
}
