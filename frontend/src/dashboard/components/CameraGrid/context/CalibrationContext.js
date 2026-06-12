import React from 'react';

export const CalibrationContext = React.createContext({
  active: false,
  cameraIdBackend: null,
  setCalibrationTarget: () => {},
});

export function CalibrationProvider({ children }) {
  const [active, setActive] = React.useState(false);
  const [cameraIdBackend, setCameraIdBackend] = React.useState(null);

  const setCalibrationTarget = React.useCallback((backendId, isActive) => {
    setCameraIdBackend(isActive ? backendId : null);
    setActive(isActive);
  }, []);

  const value = React.useMemo(
    () => ({ active, cameraIdBackend, setCalibrationTarget }),
    [active, cameraIdBackend, setCalibrationTarget],
  );

  return (
    <CalibrationContext.Provider value={value}>{children}</CalibrationContext.Provider>
  );
}

export function useCalibrationForCamera(cameraIdBackend) {
  const ctx = React.useContext(CalibrationContext);
  return {
    isActive: ctx.active && ctx.cameraIdBackend === cameraIdBackend,
    cameraIdBackend: ctx.cameraIdBackend,
    setCalibrationTarget: ctx.setCalibrationTarget,
  };
}
