export const CAMERA_OPTIONS = [
  { ui: 1, backend: 0 },
  { ui: 2, backend: 1 },
  { ui: 3, backend: 2 },
  { ui: 4, backend: 3 },
];

/** LUT 드롭다운 표시 (이름 우선, 없으면 파일명) */
export function formatLutLabel(l) {
  if (!l) return '';
  const title = l.lut_name || l.file || '';
  const steps = l.step_count ?? '-';
  const inc = l.increment_mm != null ? `${l.increment_mm}mm` : '-';
  const when = l.created_at || '';
  return when ? `${title} | ${steps}단 | Δ${inc} | ${when}` : `${title} | ${steps}단 | Δ${inc}`;
}
