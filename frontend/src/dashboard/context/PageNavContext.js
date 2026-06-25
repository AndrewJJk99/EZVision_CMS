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

export const PAGES = ['calibration', 'cms', 'settings'];

export function pathToPage(pathname) {
  if (pathname === '/settings') return 'settings';
  if (pathname === '/cms') return 'cms';
  return 'calibration';
}

export function pageToPath(page) {
  if (page === 'settings') return '/settings';
  if (page === 'cms') return '/cms';
  return '/calibration';
}
