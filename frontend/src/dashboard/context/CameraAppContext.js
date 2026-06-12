import React from 'react';

const defaultMonitors = { 1: true, 2: false, 3: false, 4: false };

export const CameraAppContext = React.createContext({
  activeCameras: defaultMonitors,
  handleCameraStateChange: () => {},
});

export function CameraAppProvider({ children }) {
  const [activeCameras, setActiveCameras] = React.useState(defaultMonitors);

  const handleCameraStateChange = React.useCallback((cameraStates) => {
    setActiveCameras({
      1: cameraStates[1]?.enabled || false,
      2: cameraStates[2]?.enabled || false,
      3: cameraStates[3]?.enabled || false,
      4: cameraStates[4]?.enabled || false,
    });
  }, []);

  const value = React.useMemo(
    () => ({ activeCameras, handleCameraStateChange }),
    [activeCameras, handleCameraStateChange],
  );

  return (
    <CameraAppContext.Provider value={value}>{children}</CameraAppContext.Provider>
  );
}

export function useCameraApp() {
  return React.useContext(CameraAppContext);
}
