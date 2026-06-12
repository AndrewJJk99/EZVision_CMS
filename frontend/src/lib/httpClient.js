const DEFAULT_TIMEOUT_MS = 10000;

const parseBody = async (response) => {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json().catch(() => ({}));
  }
  return response.text().catch(() => '');
};

export const createHttpError = (response, data) => {
  const message =
    (data && typeof data === 'object' && (data.message || data.detail || data.error)) ||
    response.statusText ||
    'Request failed';

  const error = new Error(String(message));
  error.status = response.status;
  error.code = response.status;
  error.data = data;
  return error;
};

export const request = async (url, options = {}) => {
  const controller = new AbortController();
  const timeoutMs = options.timeout ?? DEFAULT_TIMEOUT_MS;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    const data = await parseBody(response);
    if (!response.ok) {
      throw createHttpError(response, data);
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') {
      const timeoutError = new Error(`Request timeout (${timeoutMs}ms)`);
      timeoutError.code = 'TIMEOUT';
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
};

