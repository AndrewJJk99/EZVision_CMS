import React from 'react';

const PageNavContext = React.createContext({
  page: 'calibration',
  goTo: () => {},
});

export function PageNavProvider({ children, page, goTo }) {
  const value = React.useMemo(() => ({ page, goTo }), [page, goTo]);
  return <PageNavContext.Provider value={value}>{children}</PageNavContext.Provider>;
}

export function usePageNav() {
  return React.useContext(PageNavContext);
}

export const PAGES = ['calibration', 'lut', 'measurement', 'settings'];

export function pathToPage(pathname) {
  if (pathname === '/settings') return 'settings';
  if (pathname === '/measurement') return 'measurement';
  if (pathname === '/lut' || pathname === '/cms') return 'lut';
  return 'calibration';
}

export function pageToPath(page) {
  if (page === 'settings') return '/settings';
  if (page === 'measurement') return '/measurement';
  if (page === 'lut') return '/lut';
  return '/calibration';
}
