import * as React from 'react';
import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Button from '@mui/material/Button';
import ButtonGroup from '@mui/material/ButtonGroup';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Alert from '@mui/material/Alert';
import LinearProgress from '@mui/material/LinearProgress';
import Slider from '@mui/material/Slider';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import ZoomOutMapRoundedIcon from '@mui/icons-material/ZoomOutMapRounded';
import ViewInArRoundedIcon from '@mui/icons-material/ViewInArRounded';
import SaveRoundedIcon from '@mui/icons-material/SaveRounded';
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded';
import LaserColorToggle from './cms/LaserColorToggle';
import LiveCameraView from './LiveCameraView';
import { CAMERA_OPTIONS } from './cms/constants';
import { getAvailableCameras } from '../../services/camera.api';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import {
  lpcStatus, lpcStart, lpcCaptureOff, lpcCaptureOn, lpcCaptureSingle, lpcFit, lpcSave, lpcReset,
  lpGetModel, lpMeasure, lpMeasureCapture, lpMeasureFile, lpMeasureLive, lpListPlanes,
  lpCamCalStart, lpCamCalCapture, lpCamCalFit, lpCamCalReset,
} from '../../services/laserplane.api';

const errText = (e) => e?.data?.error || e?.message || '요청 실패';
const RECO_POSES = 8;
const cameraFrameSx = {
  width: '100%',
  maxWidth: 'calc(min(70vh, 780px) * 4 / 3)',
  mx: 'auto',
  aspectRatio: '4 / 3',
  bgcolor: '#0c0c0c',
  borderRadius: 1,
  overflow: 'hidden',
  border: '1px solid',
  borderColor: 'divider',
};
const rmsColor = (v, good) => (v == null ? 'default' : v <= good ? 'success' : 'warning');

function DemoRow({ label, children }) {
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between', py: 0.7, borderBottom: '1px solid', borderColor: 'divider', '&:last-child': { borderBottom: 'none' } }}>
      <Typography variant="body2" color="text.secondary" sx={{ flexShrink: 0 }}>{label}</Typography>
      <Box sx={{ minWidth: 0, textAlign: 'right' }}>{children}</Box>
    </Stack>
  );
}

export default function LaserPlaneGrid() {
  const [tab, setTab] = React.useState('measure');
  const [cam, setCam] = React.useState(0);
  // 사용 가능한 카메라 목록 — 백엔드 상태에서 동적으로 채운다(카메라 추가 시 자동 반영).
  const [cameras, setCameras] = React.useState(CAMERA_OPTIONS.map((o) => ({ ...o, connected: false, ip: null })));
  const [laserColor, setLaserColor] = React.useState('auto');
  const [captureMode, setCaptureMode] = React.useState('single'); // single | offon
  const [cols, setCols] = React.useState(12);
  const [rows, setRows] = React.useState(8);
  const [squareMm, setSquareMm] = React.useState(20);

  const [cstatus, setCstatus] = React.useState(null);
  const [overlay, setOverlay] = React.useState(null);
  const [view, setView] = React.useState('live'); // live | overlay
  const [planeName, setPlaneName] = React.useState('');
  const [planes, setPlanes] = React.useState([]);
  const [selectedPlane, setSelectedPlane] = React.useState('');
  const [model, setModel] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [msg, setMsg] = React.useState('');
  const [sev, setSev] = React.useState('info');

  // 측정: 캡처 이미지 + 클릭 두 점
  const [sensitivity, setSensitivity] = React.useState(50);
  const [draftSensitivity, setDraftSensitivity] = React.useState(50);
  const [zoom, setZoom] = React.useState(1);
  const [enlarge, setEnlarge] = React.useState(false);
  const [planeManagerOpen, setPlaneManagerOpen] = React.useState(false);
  const [draftPlane, setDraftPlane] = React.useState('');
  const [measCam, setMeasCam] = React.useState(null);
  const [measImg, setMeasImg] = React.useState(null);
  const [measSize, setMeasSize] = React.useState(null); // {width,height} 원본
  const [ptA, setPtA] = React.useState(null); // {u,v,fx,fy}
  const [ptB, setPtB] = React.useState(null);
  const [measResult, setMeasResult] = React.useState(null);
  const [gapSpec, setGapSpec] = React.useState(4);
  const [stepSpec, setStepSpec] = React.useState(1);
  const [bodyNo, setBodyNo] = React.useState('');
  const [inspectedAt, setInspectedAt] = React.useState(null);
  const [inspLogs, setInspLogs] = React.useState([]);
  // 라이브(연속) 검출 — 시연: 라인을 따라가며 엣지를 실시간 표시
  const [liveOn, setLiveOn] = React.useState(false);
  const [liveOverlay, setLiveOverlay] = React.useState(null);
  const [liveResult, setLiveResult] = React.useState(null);
  // 카메라 단독 캘리브(진단) — 레이저 없이 내부 RMS만
  const [ccCount, setCcCount] = React.useState(0);
  const [ccOverlay, setCcOverlay] = React.useState(null);
  const [ccResult, setCcResult] = React.useState(null);

  const refreshStatus = React.useCallback(async () => {
    try { const r = await lpcStatus(cam); setCstatus(r.started ? r.status : null); }
    catch (e) { setCstatus(null); }
  }, [cam]);
  const refreshPlanes = React.useCallback(async (preferFile) => {
    try {
      const r = await lpListPlanes(cam);
      const items = r?.planes || [];
      setPlanes(items);
      const pick = preferFile || (items[0] && items[0].file) || '';
      setSelectedPlane((prev) => (items.some((p) => p.file === prev) ? prev : pick));
      return items;
    } catch (e) { setPlanes([]); setSelectedPlane(''); return []; }
  }, [cam]);

  const refreshModel = React.useCallback(async (planeFile) => {
    try { setModel(await lpGetModel(cam, planeFile)); } catch (e) { setModel(null); }
  }, [cam]);

  // 연결/매핑된 카메라를 백엔드에서 조회해 선택 목록을 동적으로 구성.
  // 실패하거나 비어 있으면 기본 목록(CAMERA_OPTIONS)으로 폴백 → 파일 측정은 계속 가능.
  const refreshCameras = React.useCallback(async () => {
    try {
      const list = await getAvailableCameras();
      if (list && list.length) {
        setCameras(list);
        setCam((prev) => (list.some((c) => c.backend === prev) ? prev : list[0].backend));
      } else {
        setCameras(CAMERA_OPTIONS.map((o) => ({ ...o, connected: false, ip: null })));
      }
    } catch (e) {
      setCameras(CAMERA_OPTIONS.map((o) => ({ ...o, connected: false, ip: null })));
    }
  }, []);

  React.useEffect(() => { refreshCameras(); }, [refreshCameras]);
  React.useEffect(() => { refreshStatus(); refreshPlanes(); }, [refreshStatus, refreshPlanes]);

  // 카메라 바뀌면 라이브 중지
  React.useEffect(() => { setLiveOn(false); }, [cam]);

  // 라이브 검출 루프 — liveOn 동안 짧은 주기로 measure_live 폴링(오버레이+수치 갱신).
  // 한 번에 한 요청만(in-flight 가드) → 검출시간에 맞춰 자연스럽게 페이싱.
  React.useEffect(() => {
    if (!liveOn) return undefined;
    let alive = true;
    let timer = null;
    const tick = async () => {
      if (!alive) return;
      try {
        const r = await lpMeasureLive(cam, {
          laser_color: laserColor, detector: 'chroma',
          plane_file: selectedPlane || null, sensitivity, track: true,
        });
        if (!alive) return;
        if (r.overlay) setLiveOverlay(r.overlay);
        setLiveResult(r.edge || null);
      } catch (e) { /* 다음 프레임 재시도 */ }
      if (alive) timer = setTimeout(tick, 100);
    };
    tick();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [liveOn, cam, laserColor, selectedPlane, sensitivity]);
  React.useEffect(() => { if (selectedPlane !== undefined) refreshModel(selectedPlane); }, [selectedPlane, refreshModel]);

  const act = async (fn, showOverlay = true) => {
    setLoading(true); setMsg('');
    try {
      const r = await fn();
      if (showOverlay && r?.overlay) { setOverlay(r.overlay); setView('overlay'); }
      return r;
    } catch (e) {
      if (e?.data?.overlay) { setOverlay(e.data.overlay); setView('overlay'); }
      setSev('error'); setMsg(errText(e));
      return null;
    } finally { await refreshStatus(); setLoading(false); }
  };

  const cStart = () => act(async () => {
    const r = await lpcStart(cam, { inner_cols: Number(cols), inner_rows: Number(rows), square_size_mm: Number(squareMm) });
    setSev('success'); setMsg('통합 세션 시작 — 자세마다 OFF(코너)→ON(레이저)로 캡처하세요'); return r;
  }, false);
  const cOff = () => act(async () => {
    const r = await lpcCaptureOff(cam); setSev('success'); setMsg(`OFF 캡처됨 (코너 ${r.n_corners}). 레이저 켜고 ON 캡처하세요`); return r;
  });
  const cOn = () => act(async () => {
    const r = await lpcCaptureOn(cam, { laser_color: laserColor, detector: 'chroma' });
    setSev('success'); setMsg(`자세 ${r.pose_index} 확정 · 레이저 ${r.n_laser}점(보드위 ${r.n_onboard}) · 색 ${r.laser_color}`); return r;
  });
  const cSingle = () => act(async () => {
    const r = await lpcCaptureSingle(cam, { laser_color: laserColor, detector: 'chroma' });
    setSev('success'); setMsg(`자세 ${r.pose_index} 확정 · 레이저 ${r.n_laser}점(보드위 ${r.n_onboard}) · 색 ${r.laser_color}`); return r;
  });
  const cFit = () => act(async () => {
    const r = await lpcFit(cam);
    const base = `통합 피팅 완료 · 내부 RMS ${r.intrinsic_rms_px}px · 광평면 RMS ${r.plane_rms_mm}mm · 깊이범위 ${r.depth_span_mm ?? '—'}mm`;
    if (r.weak) { setSev('warning'); setMsg(`${base} · ⚠ 깊이 다양성 낮음 — 여러 거리에서 더 캡처 권장`); }
    else { setSev('success'); setMsg(base); }
    return r;
  }, false);
  const cSave = () => act(async () => {
    const r = await lpcSave(cam, planeName);
    await refreshPlanes(r.path);
    setSev('success'); setMsg(`저장됨: ${r.name || r.path}`); setPlaneName('');
    return r;
  }, false);
  const cReset = () => act(async () => { const r = await lpcReset(cam); setSev('info'); setMsg('초기화됨'); setOverlay(null); setView('live'); return r; }, false);

  // ── 카메라 단독 캘리브(진단) 핸들러 ──
  const ccStart = () => act(async () => {
    const r = await lpCamCalStart(cam, { inner_cols: Number(cols), inner_rows: Number(rows), square_size_mm: Number(squareMm) });
    setCcCount(0); setCcOverlay(null); setCcResult(null);
    setSev('info'); setMsg('카메라 단독 캘리브 시작 — 레이저 끄고 체커보드를 여러 자세로 캡처'); return r;
  }, false);
  const ccCapture = () => act(async () => {
    const r = await lpCamCalCapture(cam);
    if (r?.overlay) setCcOverlay(r.overlay);
    if (r?.sample_count != null) setCcCount(r.sample_count);
    setSev(r?.found ? 'success' : 'warning');
    setMsg(r?.message || (r?.found ? '코너 검출됨' : '체커보드 미검출'));
    return r;
  }, false);
  const ccFit = () => act(async () => {
    const r = await lpCamCalFit(cam);
    setCcResult(r);
    setSev(r.rms_error <= 1.0 ? 'success' : 'warning');
    setMsg(`카메라 단독 내부 RMS ${Number(r.rms_error).toFixed(3)}px · 샘플 ${r.sample_count}장${r.excluded_sample_indices?.length ? ` · outlier ${r.excluded_sample_indices.length}장 제외` : ''}`);
    return r;
  }, false);
  const ccReset = () => act(async () => {
    const r = await lpCamCalReset(cam); setCcCount(0); setCcOverlay(null); setCcResult(null);
    setSev('info'); setMsg('진단 초기화됨'); return r;
  }, false);

  const fileRef = React.useRef(null);

  const appendInspLog = (result) => {
    if (result?.distance_mm == null || result?.depth_diff_mm == null) return;
    const gap = Number(result.distance_mm);
    const step = Number(result.depth_diff_mm);
    const ng = gap > Number(gapSpec) || Math.abs(step) > Number(stepSpec);
    const at = new Date();
    setInspLogs((prev) => [{
      id: at.getTime(),
      at,
      bodyNo: bodyNo.trim() || '—',
      verdict: ng ? 'NG' : 'OK',
      gap,
      step,
      cam,
    }, ...prev].slice(0, 300));
  };

  const applyCapture = (r, srcLabel, cameraId = cam) => {
    setMeasCam(cameraId);
    setMeasImg(r.image); setMeasSize(r.image_size);
    setInspectedAt(new Date());
    if (r.auto && r.image_size) {
      const a = r.auto.a_uv, b = r.auto.b_uv;
      setPtA({ u: a[0], v: a[1], fx: a[0] / r.image_size.width, fy: a[1] / r.image_size.height });
      setPtB({ u: b[0], v: b[1], fx: b[0] / r.image_size.width, fy: b[1] / r.image_size.height });
      setMeasResult({ ...r.auto, snapped: true, auto: true });
      appendInspLog(r.auto);
      setSev(r.warning ? 'warning' : 'success');
      setMsg(`${srcLabel} · 자동 간격 ${r.auto.distance_mm} mm (${r.auto.kind || '이음부'})${r.warning ? ' · ' + r.warning : ' · 틀리면 두 점 클릭으로 보정'}`);
    } else {
      setPtA(null); setPtB(null); setMeasResult(null);
      setSev('warning'); setMsg(`${srcLabel} · 레이저 ${r.n_laser}점 · 자동 엣지 실패 → 두 점을 직접 클릭하세요${r.warning ? ' · ' + r.warning : ''}`);
    }
  };

  const onMeasCapture = async (cameraId = cam) => {
    setCam(cameraId);
    setLiveOn(false);
    setLoading(true); setMsg('');
    try {
      const r = await lpMeasureCapture(cameraId, { laser_color: laserColor, detector: 'chroma', plane_file: selectedPlane || null, sensitivity });
      applyCapture(r, '카메라 캡처', cameraId);
    } catch (e) { setSev('error'); setMsg(errText(e)); } finally { setLoading(false); }
  };

  const onMeasFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // 같은 파일 다시 선택 가능하게
    if (!file) return;
    setLoading(true); setMsg('');
    try {
      const r = await lpMeasureFile(cam, file, laserColor, 'chroma', selectedPlane || null, sensitivity);
      applyCapture(r, `파일: ${file.name}`);
    } catch (e2) { setSev('error'); setMsg(errText(e2)); } finally { setLoading(false); }
  };

  const runMeasure = async (a, b) => {
    try {
      const r = await lpMeasure(cam, { a_uv: [a.u, a.v], b_uv: [b.u, b.v], snap: true, plane_file: selectedPlane || null });
      // 스냅된 좌표로 마커 갱신
      if (measSize && r.a_uv && r.b_uv) {
        setPtA({ u: r.a_uv[0], v: r.a_uv[1], fx: r.a_uv[0] / measSize.width, fy: r.a_uv[1] / measSize.height });
        setPtB({ u: r.b_uv[0], v: r.b_uv[1], fx: r.b_uv[0] / measSize.width, fy: r.b_uv[1] / measSize.height });
      }
      setMeasResult(r); setInspectedAt(new Date()); appendInspLog(r); setSev('success'); setMsg(`거리 ${r.distance_mm} mm${r.snapped ? ' (레이저에 스냅됨)' : ''}`);
    } catch (e) { setSev('error'); setMsg(errText(e)); }
  };

  const onImgClick = (e) => {
    if (!measSize) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const fx = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const fy = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
    const pt = { u: fx * measSize.width, v: fy * measSize.height, fx, fy };
    if (!ptA || (ptA && ptB)) { setPtA(pt); setPtB(null); setMeasResult(null); }
    else { setPtB(pt); runMeasure(ptA, pt); }
  };

  // 확대/스크롤 가능한 측정 이미지 뷰 (인라인·다이얼로그 공용, 클릭 측정 동일 동작)
  const measImageView = (maxHeight, big = false, embedded = false) => (
    <Box sx={embedded ? { height: '100%' } : undefined}>
      {!embedded && (
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1, flexWrap: 'wrap', gap: 1 }}>
          <ButtonGroup size="small" variant="outlined">
            <Button onClick={() => setZoom((z) => Math.max(1, +(z - 0.5).toFixed(1)))} disabled={zoom <= 1}>－</Button>
            <Button onClick={() => setZoom(1)}>맞춤</Button>
            <Button onClick={() => setZoom((z) => Math.min(6, +(z + 0.5).toFixed(1)))} disabled={zoom >= 6}>＋</Button>
            <Button onClick={() => setZoom(3)}>원본</Button>
          </ButtonGroup>
          <Typography variant="caption" color="text.secondary">{Math.round(zoom * 100)}%{zoom > 1 ? ' · 드래그로 이동' : ''}</Typography>
          {!big && (
            <Button size="small" startIcon={<ZoomOutMapRoundedIcon />} onClick={() => setEnlarge(true)}>크게 보기</Button>
          )}
        </Stack>
      )}
      <Box sx={{ overflow: 'auto', height: embedded ? '100%' : undefined, maxHeight: embedded ? 'none' : maxHeight, border: embedded ? 'none' : '1px solid', borderColor: 'divider', borderRadius: embedded ? 0 : 2, bgcolor: '#0c0c0c' }}>
        <Box sx={{ position: 'relative', width: `${zoom * 100}%`, minWidth: '100%', lineHeight: 0 }}>
          <Box component="img" src={measImg} alt="measure" onClick={onImgClick}
            sx={{ width: '100%', display: 'block', cursor: 'crosshair' }} />
          {ptA && <Marker pt={ptA} label="A" color="#00e676" />}
          {ptB && <Marker pt={ptB} label="B" color="#ff5252" />}
          {ptA && ptB && (
            <Box component="svg" sx={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
              <line x1={`${ptA.fx * 100}%`} y1={`${ptA.fy * 100}%`} x2={`${ptB.fx * 100}%`} y2={`${ptB.fy * 100}%`}
                stroke="#ffeb3b" strokeWidth="2" strokeDasharray="6 4" />
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );

  const openPlaneManager = async () => {
    const items = await refreshPlanes(selectedPlane);
    const current = (items || []).some((p) => p.file === selectedPlane)
      ? selectedPlane
      : ((items && items[0] && items[0].file) || '');
    setDraftPlane(current);
    setDraftSensitivity(sensitivity);
    setPlaneManagerOpen(true);
  };
  const applyPlane = () => {
    if (draftPlane) setSelectedPlane(draftPlane);
    setSensitivity(draftSensitivity);
    setPlaneManagerOpen(false);
  };
  const draftMeta = planes.find((p) => p.file === draftPlane);

  const nPoses = cstatus?.n_poses ?? 0;
  const pendingOff = cstatus?.pending_off;
  const fitted = cstatus?.fitted;
  const poseProgress = Math.min(100, (nPoses / RECO_POSES) * 100);
  const gapMm = (liveOn ? liveResult?.distance_mm : measResult?.distance_mm) ?? null;
  const stepMm = (liveOn ? liveResult?.depth_diff_mm : measResult?.depth_diff_mm) ?? null;
  const gapLimit = Number(gapSpec);
  const stepLimit = Number(stepSpec);
  const hasMeasure = gapMm != null && stepMm != null && Number.isFinite(gapLimit) && Number.isFinite(stepLimit);
  const isNg = hasMeasure && (Number(gapMm) > gapLimit || Math.abs(Number(stepMm)) > stepLimit);
  const judgeLabel = loading ? '검사중' : hasMeasure ? (isNg ? 'NG' : 'OK') : inspectedAt ? '재측정' : '대기';
  const onCameras = cameras.filter((c) => c.connected);
  const shownCameras = onCameras.length
    ? onCameras
    : [{ backend: cam, ui: cameras.find((c) => c.backend === cam)?.ui ?? cam + 1 }];
  const inspectedText = inspectedAt
    ? inspectedAt.toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    : '—';

  return (
    <Box sx={{ p: { xs: 1, md: 2 }, maxWidth: 1480, mx: 'auto' }}>
      {/* 헤더 — 간략 */}
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <ViewInArRoundedIcon color="primary" />
          <Typography variant="h6" sx={{ fontWeight: 700 }}>CMS · 레이저 3D</Typography>
        </Stack>
        <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
          <TextField select size="small" label="카메라" value={cam} onChange={(e) => setCam(Number(e.target.value))} sx={{ minWidth: 170 }}>
            {cameras.map((o) => (
              <MenuItem key={o.backend} value={o.backend}>
                <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
                  <Box sx={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, bgcolor: o.connected ? 'success.main' : 'text.disabled' }} />
                  {`Camera ${o.ui}`}{o.ip ? ` · ${o.ip}` : ''}
                </Box>
              </MenuItem>
            ))}
          </TextField>
          <Tooltip title="카메라 목록 새로고침">
            <IconButton size="small" onClick={refreshCameras}><RefreshRoundedIcon fontSize="small" /></IconButton>
          </Tooltip>
        </Stack>
      </Stack>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2, minHeight: 42, borderBottom: 1, borderColor: 'divider', '& .MuiTab-root': { fontWeight: 700, minHeight: 42 } }}>
        <Tab value="measure" label="Measure" />
        <Tab value="calib" label="Calibration" />
        <Tab value="diag" label="진단" />
        <Tab value="log" label="Log" />
      </Tabs>

      {msg && <Alert severity={sev} sx={{ mb: 2, borderRadius: 2 }} onClose={() => setMsg('')}>{msg}</Alert>}

      {tab === 'diag' ? (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) 340px' }, gap: 1.5, alignItems: 'start' }}>
          <Paper elevation={0} variant="outlined" sx={{ p: 1.5, minWidth: 0 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>카메라 단독 캘리브 — 코너 검출</Typography>
            <Box sx={cameraFrameSx}>
              {ccOverlay ? (
                <Box component="img" src={ccOverlay} alt="corner overlay"
                  sx={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
              ) : (
                <Box sx={{ display: 'block', width: '100%', height: '100%' }}>
                  <LiveCameraView cameraIdBackend={cam} height="100%" flush />
                </Box>
              )}
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
              캡처하면 검출된 코너가 격자로 표시됩니다 — <b>코너가 교차점마다 정확히 박혀야</b> 내부 RMS가 낮습니다. 삐뚤거나 밀리면 그 자세가 문제.
            </Typography>
          </Paper>

          <Stack spacing={1.5}>
            <Paper elevation={0} variant="outlined" sx={{ p: 1.5 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>레이저 없이 카메라만 (내부 RMS 진단)</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                레이저를 <b>끄고</b> 체커보드만 여러 거리·각도로 캡처 → 내부 RMS만 분리해서 확인. (통합 캘리브와 별개, 저장 안 함)
              </Typography>
              <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                <TextField size="small" label="열" type="number" value={cols} onChange={(e) => setCols(e.target.value)} sx={{ flex: 1 }} />
                <TextField size="small" label="행" type="number" value={rows} onChange={(e) => setRows(e.target.value)} sx={{ flex: 1 }} />
                <TextField size="small" label="칸mm" type="number" value={squareMm} onChange={(e) => setSquareMm(e.target.value)} sx={{ flex: 1 }} />
              </Stack>
              <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                <Button variant="outlined" size="small" onClick={ccStart} disabled={loading} sx={{ flex: 1 }}>시작</Button>
                <Button variant="contained" size="small" onClick={ccCapture} disabled={loading} sx={{ flex: 1 }}>캡처</Button>
                <Button variant="outlined" color="inherit" size="small" onClick={ccReset} disabled={loading}>초기화</Button>
              </Stack>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
                <Chip size="small" label={`샘플 ${ccCount}장`} color={ccCount >= 8 ? 'success' : 'default'} />
                <Button variant="contained" color="secondary" size="small" onClick={ccFit} disabled={loading || ccCount < 3} sx={{ flex: 1 }}>
                  내부 RMS 계산
                </Button>
              </Stack>
            </Paper>

            {ccResult && (
              <Paper elevation={0} variant="outlined" sx={{ p: 1.5 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>결과</Typography>
                <Box sx={{ py: 1, mb: 1, borderRadius: 1, textAlign: 'center', color: '#fff',
                  bgcolor: ccResult.rms_error <= 0.5 ? 'success.main' : ccResult.rms_error <= 1.0 ? 'warning.main' : 'error.main' }}>
                  <Typography variant="h4" sx={{ fontWeight: 800, lineHeight: 1.1 }}>{Number(ccResult.rms_error).toFixed(3)}<Typography component="span" variant="body2"> px</Typography></Typography>
                  <Typography variant="caption">내부 RMS ({ccResult.rms_error <= 0.5 ? '좋음' : ccResult.rms_error <= 1.0 ? '양호' : '높음 — 코너 문제'})</Typography>
                </Box>
                <DemoRow label="샘플 수"><Typography variant="body2" sx={{ fontWeight: 700 }}>{ccResult.sample_count}장</Typography></DemoRow>
                <DemoRow label="fx / fy"><Typography variant="body2" sx={{ fontWeight: 700 }}>{Math.round(ccResult.focal_length_px?.fx)} / {Math.round(ccResult.focal_length_px?.fy)}</Typography></DemoRow>
                {ccResult.excluded_sample_indices?.length > 0 && (
                  <DemoRow label="제외된 자세"><Typography variant="body2" sx={{ fontWeight: 700, color: 'error.main' }}>#{ccResult.excluded_sample_indices.map((i) => i + 1).join(', ')}</Typography></DemoRow>
                )}
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, mb: 0.5, fontWeight: 700 }}>자세별 오차 (px)</Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {(ccResult.all_per_view_errors || ccResult.per_view_errors || []).map((e, i) => (
                    <Chip key={i} size="small" label={`#${i + 1}: ${Number(e).toFixed(2)}`}
                      color={e > 1.0 ? 'error' : e > 0.5 ? 'warning' : 'default'}
                      variant={ccResult.excluded_sample_indices?.includes(i) ? 'filled' : 'outlined'} />
                  ))}
                </Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                  빨강 = 오차 큰 자세(그 캡처가 문제). 특정 자세만 크면 그 자세를 빼고 다시, 전부 크면 보드 초점·정지·패턴설정 점검.
                </Typography>
              </Paper>
            )}
          </Stack>
        </Box>
      ) : tab === 'calib' ? (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) 320px' }, gap: 1.5, alignItems: 'start' }}>
          <Paper elevation={0} variant="outlined" sx={{ p: 1.5, minWidth: 0 }}>
            <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                {view === 'live' ? '라이브 카메라' : '최근 캡처 검출'}
              </Typography>
              <Tabs
                value={view} onChange={(_, v) => setView(v)}
                sx={{ minHeight: 30, '& .MuiTab-root': { minHeight: 30, py: 0, fontSize: 12, minWidth: 64 } }}
              >
                <Tab value="live" label="LIVE" />
                <Tab value="overlay" label="Detect" disabled={!overlay} />
              </Tabs>
            </Stack>
            <Box sx={cameraFrameSx}>
              <Box sx={{ display: view === 'live' ? 'block' : 'none', width: '100%', height: '100%' }}>
                <LiveCameraView cameraIdBackend={cam} height="100%" flush />
              </Box>
              {view === 'overlay' && overlay && (
                <Box component="img" src={overlay} alt="capture overlay"
                  sx={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
              )}
            </Box>
            {view === 'overlay' && overlay && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                <span style={{ color: '#e53935' }}>●</span> 코너 ·{' '}
                <span style={{ color: '#2e7d32' }}>●</span> 보드 위 레이저 ·{' '}
                <span style={{ color: '#9e9e9e' }}>●</span> 제외(보드 밖)
              </Typography>
            )}
          </Paper>

          <Paper elevation={0} variant="outlined" sx={{ p: 1.5 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>세션</Typography>
            <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
              <TextField size="small" label="열" type="number" value={cols} onChange={(e) => setCols(e.target.value)} sx={{ flex: 1 }} />
              <TextField size="small" label="행" type="number" value={rows} onChange={(e) => setRows(e.target.value)} sx={{ flex: 1 }} />
              <TextField size="small" label="칸" type="number" value={squareMm} onChange={(e) => setSquareMm(e.target.value)} sx={{ flex: 1 }} />
            </Stack>
            <Button fullWidth variant={cstatus ? 'outlined' : 'contained'} size="small" onClick={cStart} disabled={loading}>
              {cstatus ? '세션 재시작' : '세션 시작'}
            </Button>

            <Typography variant="subtitle2" sx={{ fontWeight: 700, mt: 2, mb: 1 }}>자세 캡처</Typography>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
              <Chip size="small" label={`${nPoses} / ${RECO_POSES}+`} color={nPoses >= RECO_POSES ? 'success' : 'default'} />
              <LinearProgress variant="determinate" value={poseProgress} sx={{ flex: 1, height: 6, borderRadius: 3 }} />
            </Stack>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1, flexWrap: 'wrap', gap: 1 }}>
              <ToggleButtonGroup size="small" exclusive value={captureMode}
                onChange={(_e, v) => { if (v) setCaptureMode(v); }}>
                <ToggleButton value="single" sx={{ px: 1.25, py: 0.25, fontSize: 12 }}>단일</ToggleButton>
                <ToggleButton value="offon" sx={{ px: 1.25, py: 0.25, fontSize: 12 }}>OFF·ON</ToggleButton>
              </ToggleButtonGroup>
              <LaserColorToggle value={laserColor} onChange={setLaserColor} disabled={loading} />
            </Stack>
            {captureMode === 'single' ? (
              <Button fullWidth variant="contained" size="small" onClick={cSingle} disabled={loading || !cstatus}>자세 캡처</Button>
            ) : (
              <Stack spacing={1}>
                <Stack direction="row" spacing={1}>
                  <Button fullWidth variant={pendingOff ? 'outlined' : 'contained'} size="small"
                    onClick={cOff} disabled={loading || !cstatus}>OFF</Button>
                  <Button fullWidth variant="contained" color="secondary" size="small"
                    onClick={cOn} disabled={loading || !pendingOff}>ON</Button>
                </Stack>
                {pendingOff && (
                  <Typography variant="caption" color="text.secondary">OFF 완료. 레이저를 켜고 ON.</Typography>
                )}
              </Stack>
            )}

            <Typography variant="subtitle2" sx={{ fontWeight: 700, mt: 2, mb: 0.5 }}>피팅 · 저장</Typography>
            <DemoRow label="내부 RMS">
              <Typography variant="body2" sx={{ fontWeight: 700, color: rmsColor(cstatus?.intrinsic_rms_px, 0.6) === 'success' ? 'success.main' : 'text.primary' }}>
                {cstatus?.intrinsic_rms_px ?? '—'} px
              </Typography>
            </DemoRow>
            <DemoRow label="광평면 RMS">
              <Typography variant="body2" sx={{ fontWeight: 700, color: rmsColor(cstatus?.plane_rms_mm, 0.6) === 'success' ? 'success.main' : 'text.primary' }}>
                {cstatus?.plane_rms_mm ?? '—'} mm
              </Typography>
            </DemoRow>
            <TextField size="small" fullWidth label="저장 이름" placeholder="예: rig-A 0922"
              value={planeName} onChange={(e) => setPlaneName(e.target.value)} disabled={loading || !fitted} sx={{ mt: 1, mb: 1 }} />
            <Stack direction="row" spacing={1}>
              <Button variant="contained" size="small" onClick={cFit} disabled={loading || nPoses < 4}>피팅</Button>
              <Button variant="outlined" color="success" size="small" startIcon={<SaveRoundedIcon />} onClick={cSave} disabled={loading || !fitted}>저장</Button>
              <Button variant="text" color="error" size="small" onClick={cReset} disabled={loading || !cstatus}>초기화</Button>
            </Stack>
          </Paper>
        </Box>
      ) : tab === 'log' ? (
        <Paper elevation={0} variant="outlined" sx={{ p: 2, minHeight: 480, display: 'flex', flexDirection: 'column' }}>
          <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>검사 로그</Typography>
            <Button size="small" color="inherit" onClick={() => setInspLogs([])} disabled={inspLogs.length === 0}>지우기</Button>
          </Stack>
          <TableContainer sx={{ flex: 1, maxHeight: '70vh' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  {['시간', '바디넘버', '판정', '간격', '단차', '카메라'].map((h) => (
                    <TableCell key={h} sx={{ fontWeight: 700 }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {inspLogs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6}>
                      <Typography variant="body2" color="text.secondary">검사 로그가 없습니다.</Typography>
                    </TableCell>
                  </TableRow>
                ) : inspLogs.map((row) => {
                  const camUi = cameras.find((o) => o.backend === row.cam)?.ui
                    ?? CAMERA_OPTIONS.find((o) => o.backend === row.cam)?.ui
                    ?? row.cam + 1;
                  const atText = row.at.toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
                  return (
                    <TableRow key={row.id} hover>
                      <TableCell>{atText}</TableCell>
                      <TableCell>{row.bodyNo}</TableCell>
                      <TableCell>
                        <Chip size="small" label={row.verdict} color={row.verdict === 'NG' ? 'error' : 'success'} />
                      </TableCell>
                      <TableCell>{row.gap} mm</TableCell>
                      <TableCell>{row.step} mm</TableCell>
                      <TableCell>{`Camera ${camUi ?? row.cam}`}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      ) : (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) 320px' }, gap: 1.5, alignItems: 'start' }}>
          <Box sx={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(shownCameras.length, 1)}, minmax(0, 1fr))`, gap: 1.5, minWidth: 0 }}>
            {shownCameras.map((c) => {
              const showingStill = measImg && measCam === c.backend && !liveOn;
              const showingDetect = liveOn && cam === c.backend;
              return (
                <Paper key={c.backend} elevation={0} variant="outlined" sx={{ p: 1.5, minWidth: 0, outline: cam === c.backend ? '2px solid' : 'none', outlineColor: 'primary.main' }}>
                  <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1, flexWrap: 'wrap', gap: 0.5 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Camera {c.ui}</Typography>
                    <Stack direction="row" spacing={0.5}>
                      <Button
                        size="small"
                        variant={showingDetect ? 'outlined' : 'text'}
                        color={showingDetect ? 'error' : 'primary'}
                        onClick={() => { setCam(c.backend); setLiveOn((v) => (cam === c.backend ? !v : true)); }}
                      >
                        {showingDetect ? '라이브 중지' : '라이브'}
                      </Button>
                      <Button size="small" variant="contained" onClick={() => onMeasCapture(c.backend)} disabled={loading || !model}>검사</Button>
                      {showingStill && (
                        <Button size="small" onClick={() => setMeasCam(null)}>LIVE</Button>
                      )}
                    </Stack>
                  </Stack>
                  <Box sx={{ width: '100%', aspectRatio: '4 / 3', bgcolor: '#0c0c0c', borderRadius: 1, overflow: 'hidden' }}>
                    {showingStill ? measImageView('100%', false, true) : showingDetect ? (
                      liveOverlay ? (
                        <Box component="img" src={liveOverlay} alt="" sx={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
                      ) : (
                        <Box sx={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <Typography variant="caption" sx={{ color: '#888' }}>검출 중…</Typography>
                        </Box>
                      )
                    ) : (
                      <LiveCameraView cameraIdBackend={c.backend} height="100%" flush />
                    )}
                  </Box>
                  {showingStill && (
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mt: 1, flexWrap: 'wrap', gap: 1 }}>
                      <ButtonGroup size="small" variant="outlined">
                        <Button onClick={() => setZoom((z) => Math.max(1, +(z - 0.5).toFixed(1)))} disabled={zoom <= 1}>－</Button>
                        <Button onClick={() => setZoom(1)}>맞춤</Button>
                        <Button onClick={() => setZoom((z) => Math.min(6, +(z + 0.5).toFixed(1)))} disabled={zoom >= 6}>＋</Button>
                        <Button onClick={() => setZoom(3)}>원본</Button>
                      </ButtonGroup>
                      <Button size="small" startIcon={<ZoomOutMapRoundedIcon />} onClick={() => setEnlarge(true)}>크게 보기</Button>
                    </Stack>
                  )}
                </Paper>
              );
            })}
          </Box>

          <Stack spacing={1.5}>
          <Paper elevation={0} variant="outlined" sx={{ p: 1.5 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>판정 결과</Typography>
            <Box sx={{
              mb: 1,
              py: 0.75,
              borderRadius: 1,
              textAlign: 'center',
              color: 'common.white',
              bgcolor: !hasMeasure ? 'grey.700' : isNg ? 'error.main' : 'success.main',
            }}>
              <Typography variant="h5" sx={{ fontWeight: 800, lineHeight: 1.2 }}>
                {hasMeasure ? (isNg ? 'NG' : 'OK') : '—'}
              </Typography>
            </Box>
            <DemoRow label="검사상태">
              <Typography variant="body2" sx={{ fontWeight: 700 }}>{judgeLabel}</Typography>
            </DemoRow>
            <DemoRow label="검사시간">
              <Typography variant="body2" sx={{ fontWeight: 700 }}>{inspectedText}</Typography>
            </DemoRow>
            <DemoRow label="바디넘버">
              <TextField size="small" placeholder="—" value={bodyNo} onChange={(e) => setBodyNo(e.target.value)}
                sx={{ width: 140, '& .MuiInputBase-input': { py: 0.4, fontWeight: 700, textAlign: 'right', fontSize: 14 } }} />
            </DemoRow>
            <DemoRow label="간격">
              <Typography variant="body2" sx={{ fontWeight: 700, color: hasMeasure && Number(gapMm) > gapLimit ? 'error.main' : 'text.primary' }}>
                {gapMm == null ? '—' : `${gapMm} mm`}
              </Typography>
            </DemoRow>
            <DemoRow label="단차">
              <Typography variant="body2" sx={{ fontWeight: 700, color: hasMeasure && Math.abs(Number(stepMm)) > stepLimit ? 'error.main' : 'text.primary' }}>
                {stepMm == null ? '—' : `${stepMm} mm`}
              </Typography>
            </DemoRow>
            <DemoRow label="간격 기준">
              <TextField size="small" type="number" value={gapSpec} onChange={(e) => setGapSpec(e.target.value)}
                sx={{ width: 88, '& .MuiInputBase-input': { py: 0.4, fontWeight: 700, textAlign: 'right', fontSize: 14 } }} />
            </DemoRow>
            <DemoRow label="단차 기준">
              <TextField size="small" type="number" value={stepSpec} onChange={(e) => setStepSpec(e.target.value)}
                sx={{ width: 88, '& .MuiInputBase-input': { py: 0.4, fontWeight: 700, textAlign: 'right', fontSize: 14 } }} />
            </DemoRow>
          </Paper>
          <Paper elevation={0} variant="outlined" sx={{ p: 1.5 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>설정</Typography>
            <Stack spacing={1.25}>
              <Button fullWidth size="small" variant="outlined" onClick={openPlaneManager}>Manager</Button>
              <LaserColorToggle value={laserColor} onChange={setLaserColor} disabled={loading} />
              <Button fullWidth size="small" variant="outlined" onClick={() => fileRef.current?.click()} disabled={loading || !model}>PC 이미지</Button>
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={onMeasFile} />
            </Stack>
          </Paper>
          </Stack>
        </Box>
      )}

      {/* 전체화면 확대 (측정 탭처럼) — 안에서 확대·클릭 측정 가능 */}
      <Dialog open={planeManagerOpen} onClose={() => setPlaneManagerOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle sx={{ fontWeight: 700, pb: 1 }}>Calibration Manager</DialogTitle>
        <DialogContent>
          {planes.length === 0 ? (
            <Alert severity="info" sx={{ borderRadius: 2 }}>저장된 캘리브레이션이 없습니다. Calibration 탭에서 피팅·저장하세요.</Alert>
          ) : (
            <>
              <TextField select fullWidth size="small" label="캘리브레이션" value={draftPlane} onChange={(e) => setDraftPlane(e.target.value)}
                sx={{ mt: 1 }} InputLabelProps={{ shrink: true }}>
                {planes.map((p) => (
                  <MenuItem key={p.file} value={p.file}>{p.name || p.file}</MenuItem>
                ))}
              </TextField>
              {draftMeta && (
                <Stack direction="row" spacing={1} sx={{ mt: 2, flexWrap: 'wrap', gap: 1 }}>
                  {draftMeta.fit_rms_mm != null && <Chip size="small" color="success" label={`RMS ${draftMeta.fit_rms_mm} mm`} />}
                  {draftMeta.created_at && <Chip size="small" variant="outlined" label={draftMeta.created_at} />}
                  <Chip size="small" variant="outlined" label={draftMeta.file} />
                </Stack>
              )}
            </>
          )}
          <Box sx={{ mt: 3 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>자동 엣지 민감도</Typography>
            <Typography variant="caption" color="text.secondary">{draftSensitivity} · 낮으면 엄격, 높으면 약한 엣지도 잡습니다</Typography>
            <Slider size="small" value={draftSensitivity} onChange={(_e, v) => setDraftSensitivity(v)}
              min={0} max={100} step={5} valueLabelDisplay="auto"
              marks={[{ value: 0, label: '엄격' }, { value: 100, label: '민감' }]}
              sx={{ mt: 1, mx: 0.5 }} />
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setPlaneManagerOpen(false)}>취소</Button>
          <Button variant="contained" onClick={applyPlane} disabled={planes.length > 0 && !draftPlane}>확인</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={enlarge} onClose={() => setEnlarge(false)} fullWidth maxWidth="xl">
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 2, py: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            측정 이미지 확대 — 레이저 위 두 점 클릭{measResult ? ` · ${measResult.distance_mm} mm` : ''}
          </Typography>
          <IconButton size="small" onClick={() => setEnlarge(false)}><CloseRoundedIcon /></IconButton>
        </Box>
        <Box sx={{ px: 2, pb: 2 }}>
          {measImg && measImageView('82vh', true)}
        </Box>
      </Dialog>
    </Box>
  );
}

function Marker({ pt, label, color }) {
  return (
    <Box sx={{ position: 'absolute', left: `${pt.fx * 100}%`, top: `${pt.fy * 100}%`, transform: 'translate(-50%,-50%)', pointerEvents: 'none' }}>
      <Box sx={{ width: 14, height: 14, borderRadius: '50%', border: '2px solid #fff', bgcolor: color, boxShadow: 1 }} />
      <Typography variant="caption" sx={{ position: 'absolute', left: 16, top: -4, color: '#fff', fontWeight: 700, textShadow: '0 0 3px #000' }}>{label}</Typography>
    </Box>
  );
}
