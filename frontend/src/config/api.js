const trimTrailingSlash = (value) => String(value || '').replace(/\/+$/, '');

const DEFAULTS = {
  ui: process.env.REACT_APP_UI_API || 'http://localhost:8000',
  camera: process.env.REACT_APP_CAMERA_API || 'http://localhost:7070',
  cms: process.env.REACT_APP_CMS_API || 'http://localhost:7060',
};

const STORAGE_KEY = (key) => `ezvision_cms_api_${key}`;

const fromStorage = (key) => {
  try {
    return localStorage.getItem(STORAGE_KEY(key));
  } catch {
    return null;
  }
};

const readApi = () => ({
  ui: trimTrailingSlash(fromStorage('ui') || DEFAULTS.ui),
  camera: trimTrailingSlash(fromStorage('camera') || DEFAULTS.camera),
  cms: trimTrailingSlash(fromStorage('cms') || DEFAULTS.cms),
});

export const API = readApi();
