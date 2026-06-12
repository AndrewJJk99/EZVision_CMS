import * as React from 'react';
import Badge from '@mui/material/Badge';

function MenuButton({ showBadge = false, ...props }) {
  if (showBadge) {
    return (
      <Badge color="error" variant="dot">
        <button {...props} />
      </Badge>
    );
  }
  return <button {...props} />;
}

MenuButton.propTypes = {};

export default MenuButton;


