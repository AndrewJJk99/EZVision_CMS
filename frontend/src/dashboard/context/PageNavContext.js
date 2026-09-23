import React from 'react';

const PageNavContext = React.createContext({
  page: 'cms',
  goTo: () => {},
});

export function PageNavProvider({ children, page, goTo }) {
  const value = React.useMemo(() => ({ page, goTo }), [page, goTo]);
  return <PageNavContext.Provider value={value}>{children}</PageNavContext.Provider>;
}

export function usePageNav() {
  return React.useContext(PageNavContext);
}

export const PAGES = ['cms', 'settings'];

export function pathToPage(pathname) {
  if (pathname === '/settings') return 'settings';
  return 'cms';
}

export function pageToPath(page) {
  if (page === 'settings') return '/settings';
  return '/cms';
}
