import * as React from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import { getCameraWsUrl, getCameraStatus, startCamera } from '../../services/camera.api';

/**
 * 라이브 카메라 뷰 — /camera/ws/{id} JPEG 프레임을 <img>에 표시.
 * 스스로 카메라 상태를 확인하고, 그래빙이 꺼져 있으면 시작한 뒤 스트리밍한다.
 * 기존 모니터(CameraSessions)와 독립.
 */
export default function LiveCameraView({ cameraIdBackend, height = 440, flush = false }) {
  const imgRef = React.useRef(null);
  const wsRef = React.useRef(null);
  const prevUrlRef = React.useRef(null);
  const closedRef = React.useRef(false);
  const timerRef = React.useRef(null);
  const [state, setState] = React.useState('init'); // init | starting | connecting | live | offline
  const [note, setNote] = React.useState('');

  const cleanup = React.useCallback(() => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    if (wsRef.current) { try { wsRef.current.close(); } catch (e) { /* ignore */ } wsRef.current = null; }
    if (prevUrlRef.current) { URL.revokeObjectURL(prevUrlRef.current); prevUrlRef.current = null; }
  }, []);

  const connectWs = React.useCallback(() => {
    if (closedRef.current) return;
    setState((s) => (s === 'live' ? s : 'connecting'));
    let ws;
    try {
      ws = new WebSocket(getCameraWsUrl(cameraIdBackend));
    } catch (e) {
      timerRef.current = setTimeout(connectWs, 2000);
      return;
    }
    ws.binaryType = 'blob';
    wsRef.current = ws;
    ws.onopen = () => { if (!closedRef.current) setState('live'); };
    ws.onmessage = (ev) => {
      const blob = ev.data instanceof Blob ? ev.data : new Blob([ev.data], { type: 'image/jpeg' });
      const url = URL.createObjectURL(blob);
      if (imgRef.current) imgRef.current.src = url;
      if (prevUrlRef.current) URL.revokeObjectURL(prevUrlRef.current);
      prevUrlRef.current = url;
      if (!closedRef.current) setState('live');
    };
    ws.onerror = () => { try { ws.close(); } catch (e) { /* ignore */ } };
    ws.onclose = () => {
      if (closedRef.current) return;
      // 그래빙이 꺼져 있으면 WS가 바로 닫힌다 → 상태 확인 후 재시도
      timerRef.current = setTimeout(ensureAndConnect, 2000);
    };
  }, [cameraIdBackend]); // eslint-disable-line react-hooks/exhaustive-deps

  const ensureAndConnect = React.useCallback(async () => {
    if (closedRef.current) return;
    try {
      const res = await getCameraStatus(cameraIdBackend);
      const st = res?.status;
      const running = st && (st.is_running ?? st?.status?.is_running);
      const hasCam = st && (st.has_camera ?? st?.status?.has_camera);
      if (hasCam === false) {
        setState('offline');
        setNote('카메라가 매핑/초기화되지 않았습니다 (Settings에서 IP 매핑 확인)');
        timerRef.current = setTimeout(ensureAndConnect, 4000);
        return;
      }
      if (!running) {
        setState('starting');
        setNote('카메라 그래빙 시작 중…');
        try { await startCamera(); } catch (e) { /* ignore */ }
      }
    } catch (e) {
      setState('offline');
      setNote('카메라 API 응답 없음 (Camera 서버 7070 확인)');
      timerRef.current = setTimeout(ensureAndConnect, 4000);
      return;
    }
    connectWs();
  }, [cameraIdBackend, connectWs]);

  React.useEffect(() => {
    closedRef.current = false;
    setState('init'); setNote('');
    ensureAndConnect();
    return () => { closedRef.current = true; cleanup(); };
  }, [cameraIdBackend, ensureAndConnect, cleanup]);

  const manualStart = async () => {
    setState('starting'); setNote('카메라 그래빙 시작 중…');
    try { await startCamera(); } catch (e) { /* ignore */ }
    ensureAndConnect();
  };

  return (
    <Box
      sx={{
        position: 'relative', height, width: '100%', bgcolor: '#0c0c0c',
        borderRadius: flush ? 0 : 1,
        overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: flush ? 'none' : '1px solid', borderColor: 'divider',
      }}
    >
      {/* eslint-disable-next-line jsx-a11y/img-redundant-alt */}
      <img
        ref={imgRef}
        alt=""
        style={{
          maxWidth: '100%', maxHeight: '100%', objectFit: 'contain',
          visibility: state === 'live' ? 'visible' : 'hidden',
        }}
      />
      {state !== 'live' && (
        <Box sx={{ position: 'absolute', textAlign: 'center', px: 2 }}>
          <Typography variant="body2" sx={{ color: '#ccc' }}>
            {state === 'offline' ? '카메라 연결 불가' : state === 'starting' ? '카메라 시작 중…' : '카메라 연결 중…'}
          </Typography>
          {note && <Typography variant="caption" sx={{ color: '#888', display: 'block', mt: 0.5 }}>{note}</Typography>}
          {state === 'offline' && (
            <Button size="small" variant="outlined" onClick={manualStart} sx={{ mt: 1 }}>
              카메라 시작 재시도
            </Button>
          )}
        </Box>
      )}
      <Box sx={{ position: 'absolute', top: 8, left: 10 }}>
        <Box component="span" sx={{
          display: 'inline-flex', alignItems: 'center', gap: 0.75,
          bgcolor: 'rgba(0,0,0,0.55)', color: '#fff', px: 1, py: 0.25, borderRadius: 1, fontSize: 12,
        }}>
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: state === 'live' ? '#4caf50' : '#e53935' }} />
          {state === 'live' ? 'LIVE' : 'OFF'}
        </Box>
      </Box>
    </Box>
  );
}
