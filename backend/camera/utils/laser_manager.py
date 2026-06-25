"""
라인 레이저 기반 높이(단차) 측정 유틸.

파이프라인:
  왜곡보정 이미지 → 파란 레이저 선 검출(프로파일: x→y) →
  [계단블록] 프로파일을 단(plateau)으로 분할 → LUT(y_pixel→height_mm) 생성/저장 →
  [측정] 두 구간 평균 y → LUT 보간 → 단차 = height_A − height_B
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List, Optional, Tuple

import cv2
import numpy as np

# 파란 레이저 기본 HSV 범위 (OpenCV: H 0~179)
DEFAULT_H_LOW = 90
DEFAULT_H_HIGH = 130
DEFAULT_S_MIN = 80
DEFAULT_V_MIN = 80


def _reject_outliers_continuity(
    profile: np.ndarray, max_jump: float, win: int = 15
) -> np.ndarray:
    """레이저 선은 연속적이므로, 이웃 중앙값에서 max_jump 이상 벗어난 점은 제거."""
    if max_jump is None or max_jump <= 0:
        return profile
    w = len(profile)
    out = profile.copy()
    for x in range(w):
        if np.isnan(profile[x]):
            continue
        lo = max(0, x - win)
        hi = min(w, x + win + 1)
        neigh = profile[lo:hi]
        neigh = neigh[~np.isnan(neigh)]
        if neigh.size < 3:
            continue
        if abs(profile[x] - np.median(neigh)) > max_jump:
            out[x] = np.nan
    return out


def _build_mask_weight(
    undistorted_bgr: np.ndarray,
    method: str,
    h_low: int,
    h_high: int,
    s_min: int,
    v_min: int,
    blue_boost: bool,
    thresh_offset: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """검출용 (mask, weight) 생성.

    method="auto": 밝기 기반 자동(Otsu) — 색 튜닝 거의 불필요
    method="hsv" : 파란색 범위 기반(수동)
    """
    if method == "hsv":
        hsv = cv2.cvtColor(undistorted_bgr, cv2.COLOR_BGR2HSV)
        lower = np.array([int(h_low), int(s_min), int(v_min)], dtype=np.uint8)
        upper = np.array([int(h_high), 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        mask = cv2.medianBlur(mask, 3)
        weight = undistorted_bgr[:, :, 0].astype(np.float64)
        weight = np.where(mask > 0, weight, 0.0)
        return mask, weight

    # 자동(밝기) 모드
    gray = cv2.cvtColor(undistorted_bgr, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.GaussianBlur(gray, (3, 3), 0)
    otsu_t, _ = cv2.threshold(gray_blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    t = int(min(255, max(0, otsu_t + int(thresh_offset))))
    mask = (gray >= t).astype(np.uint8) * 255
    mask = cv2.medianBlur(mask, 3)

    weight = gray.astype(np.float64)
    if blue_boost:
        b = undistorted_bgr[:, :, 0].astype(np.float64)
        g = undistorted_bgr[:, :, 1].astype(np.float64)
        r = undistorted_bgr[:, :, 2].astype(np.float64)
        blueness = np.clip(b - np.maximum(g, r), 0, 255) / 255.0
        weight = weight * (0.5 + blueness)  # 파란 픽셀에 가산점
    weight = np.where(mask > 0, weight, 0.0)
    return mask, weight


def _keep_longest_line(mask: np.ndarray, bridge_gap: int) -> np.ndarray:
    """가로로 끊긴 부분을 이어붙인 뒤, 가장 긴(가장 넓은) 연결요소만 남긴다.

    레이저 선은 가로로 길게 이어지고, 반사는 보통 따로 떨어진 덩어리라
    'x 방향으로 가장 넓게 퍼진' 연결요소가 진짜 레이저 선이다.
    """
    if mask is None or not np.any(mask):
        return mask
    work = mask.copy()
    if bridge_gap and bridge_gap > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(bridge_gap), 1))
        work = cv2.morphologyEx(work, cv2.MORPH_CLOSE, kernel)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(work, 8)
    if num <= 2:  # 배경 + (최대) 1개 → 그대로
        return mask

    best, best_score = -1, -1
    for i in range(1, num):
        # '가장 긴 선' = x 방향 폭이 가장 넓은 것, 동률이면 면적
        score = stats[i, cv2.CC_STAT_WIDTH] * 100000 + stats[i, cv2.CC_STAT_AREA]
        if score > best_score:
            best_score, best = score, i
    if best < 0:
        return mask
    return np.where(labels == best, mask, 0).astype(mask.dtype)


def detect_laser_profile(
    undistorted_bgr: np.ndarray,
    h_low: int = DEFAULT_H_LOW,
    h_high: int = DEFAULT_H_HIGH,
    s_min: int = DEFAULT_S_MIN,
    v_min: int = DEFAULT_V_MIN,
    min_col_weight: float = 20.0,
    min_area: int = 30,
    peak_band: int = 12,
    max_jump: float = 25.0,
    roi_y0: Optional[int] = None,
    roi_y1: Optional[int] = None,
    method: str = "auto",
    blue_boost: bool = True,
    thresh_offset: int = 0,
    keep_largest: bool = True,
    bridge_gap: int = 25,
) -> Tuple[np.ndarray, np.ndarray]:
    """각 x열에서 레이저 밝기 가중 중심 y를 서브픽셀로 계산.

    method="auto": 밝기 기반 자동(Otsu) — 튜닝 거의 불필요(기본)
    method="hsv" : 파란색 범위 수동 지정

    반사광 자동 제거:
      - keep_largest: 점이 이어진 '가장 긴 선' 하나만 남기고 나머지(반사) 버림
      - bridge_gap: 끊긴 선을 가로로 이어붙일 간격(px)
      - roi_y0/roi_y1: 레이저가 지나는 세로 밴드만 검사(선택)

    반환: (profile[w] (검출 안 된 열은 NaN), mask)
    """
    mask, weight = _build_mask_weight(
        undistorted_bgr, method, h_low, h_high, s_min, v_min, blue_boost, thresh_offset
    )
    h, w = mask.shape

    # ROI: 레이저가 지나는 세로 구간 밖은 무시
    if roi_y0 is not None or roi_y1 is not None:
        y0 = 0 if roi_y0 is None else max(0, min(int(roi_y0), h))
        y1 = h if roi_y1 is None else max(0, min(int(roi_y1), h))
        if y1 > y0:
            band = np.zeros_like(mask)
            band[y0:y1, :] = mask[y0:y1, :]
            mask = band

    # 작은 반사 반점 제거 (연결요소 면적 필터)
    if min_area and min_area > 0:
        num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        keep = np.zeros_like(mask)
        for i in range(1, num):
            if stats[i, cv2.CC_STAT_AREA] >= int(min_area):
                keep[labels == i] = 255
        mask = keep

    # 핵심: 점이 이어진 '가장 긴 선' 하나만 남기고 반사는 버림
    if keep_largest:
        mask = _keep_longest_line(mask, int(bridge_gap))

    # ROI/면적 필터로 줄어든 mask를 weight에 다시 반영
    weight = np.where(mask > 0, weight, 0.0)
    ys = np.arange(h, dtype=np.float64).reshape(h, 1)

    col_sum = weight.sum(axis=0)  # (w,)
    profile = np.full(w, np.nan, dtype=np.float64)

    if int(peak_band) > 0:
        # 가장 밝은 지점(피크) 주변 peak_band 범위만 평균 → 다른 위치의 반사 무시
        pk = np.argmax(weight, axis=0)  # (w,)
        lo = np.clip(pk - int(peak_band), 0, h).reshape(1, w)
        hi = np.clip(pk + int(peak_band) + 1, 0, h).reshape(1, w)
        yy = np.arange(h).reshape(h, 1)
        win = (yy >= lo) & (yy < hi)
        wseg = np.where(win, weight, 0.0)
        seg_sum = wseg.sum(axis=0)
        valid = (col_sum > float(min_col_weight)) & (seg_sum > 0)
        if np.any(valid):
            centroid = (wseg[:, valid] * ys).sum(axis=0) / seg_sum[valid]
            profile[valid] = centroid
    else:
        valid = col_sum > float(min_col_weight)
        if np.any(valid):
            profile[valid] = (weight[:, valid] * ys).sum(axis=0) / col_sum[valid]

    # 연속성 기반 이상점 제거 (반사로 튄 점 정리)
    profile = _reject_outliers_continuity(profile, float(max_jump))
    return profile, mask


def profile_to_points(profile: np.ndarray) -> List[list]:
    """프로파일(x→y, NaN 제외)을 [[x, y], ...] 리스트로 변환."""
    xs = np.where(~np.isnan(profile))[0]
    return [[int(x), round(float(profile[x]), 2)] for x in xs]


def points_to_profile(points: list, width: int) -> np.ndarray:
    """[[x, y], ...] 점 목록을 폭 width 프로파일 배열로 복원."""
    profile = np.full(int(width), np.nan, dtype=np.float64)
    for p in points or []:
        x = int(round(p[0]))
        if 0 <= x < width:
            profile[x] = float(p[1])
    return profile


def draw_points(
    img: np.ndarray,
    points: list,
    color: Tuple[int, int, int] = (0, 255, 255),
    radius: int = 2,
    thickness: int = 2,
    connect: bool = True,
) -> np.ndarray:
    """검출된 레이저 점을 잘 보이게 표시 (점 + 이어진 선)."""
    out = img.copy()
    pts = sorted([p for p in (points or []) if p is not None], key=lambda p: p[0])
    prev = None
    for p in pts:
        x = int(round(p[0]))
        y = int(round(p[1]))
        cv2.circle(out, (x, y), radius, color, -1)
        if connect and prev is not None and abs(x - prev[0]) <= 3:
            cv2.line(out, prev, (x, y), color, thickness)
        prev = (x, y)
    return out


def draw_profile(
    undistorted_bgr: np.ndarray,
    profile: np.ndarray,
    color: Tuple[int, int, int] = (0, 255, 255),
) -> np.ndarray:
    out = undistorted_bgr.copy()
    for x in range(len(profile)):
        y = profile[x]
        if not np.isnan(y):
            cv2.circle(out, (x, int(round(y))), 1, color, -1)
    return out


def build_lut_from_points(
    points: list,
    n_steps: int,
    increment_mm: float,
    base_mm: float = 0.0,
    reverse_order: bool = False,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """[[x, y], ...] 점 목록을 n_steps개 단으로 분할해 LUT 표 생성."""
    pts = [p for p in (points or []) if p is not None]
    if len(pts) < n_steps * 3:
        return None, "레이저 점이 너무 적습니다 (점을 너무 많이 지웠거나 검출 실패)"
    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float32)
    return _build_lut_core(xs, ys, n_steps, increment_mm, base_mm, reverse_order)


def build_lut_from_staircase(
    profile: np.ndarray,
    n_steps: int,
    increment_mm: float,
    base_mm: float = 0.0,
    reverse_order: bool = False,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """계단 프로파일을 n_steps개 단으로 분할해 LUT 표 생성."""
    xs = np.where(~np.isnan(profile))[0].astype(np.float64)
    if len(xs) < n_steps * 3:
        return None, "레이저 점이 너무 적습니다 (검출 실패 또는 범위 확인 필요)"
    ys = profile[xs.astype(int)].astype(np.float32)
    return _build_lut_core(xs, ys, n_steps, increment_mm, base_mm, reverse_order)


def _build_lut_core(
    xs: np.ndarray,
    ys: np.ndarray,
    n_steps: int,
    increment_mm: float,
    base_mm: float,
    reverse_order: bool,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """단은 x순서로 높이가 증가한다고 가정 (reverse_order로 반전 가능)."""
    data = ys.reshape(-1, 1).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    _compact, labels, _centers = cv2.kmeans(
        data, int(n_steps), None, criteria, 5, cv2.KMEANS_PP_CENTERS
    )
    labels = labels.flatten()

    clusters = []
    for k in range(int(n_steps)):
        idx = labels == k
        if not np.any(idx):
            continue
        clusters.append(
            (float(xs[idx].mean()), float(ys[idx].mean()), int(idx.sum()))
        )

    if len(clusters) < 2:
        return None, "단(계단)을 충분히 구분하지 못했습니다"

    # x 순서로 정렬 (계단을 가로지르므로 x순서 = 높이순서)
    clusters.sort(key=lambda c: c[0], reverse=reverse_order)

    table = []
    for i, (mean_x, mean_y, count) in enumerate(clusters):
        table.append(
            {
                "y_pixel": round(mean_y, 3),
                "height_mm": round(base_mm + i * increment_mm, 4),
                "mean_x": round(mean_x, 1),
                "count": count,
            }
        )
    return table, None


def _medfilt1d(a: np.ndarray, k: int) -> np.ndarray:
    if k is None or k < 3:
        return a
    k = int(k) | 1
    r = k // 2
    n = len(a)
    out = a.copy()
    for i in range(n):
        lo = max(0, i - r)
        hi = min(n, i + r + 1)
        out[i] = np.median(a[lo:hi])
    return out


def _step_detect_params(sensitivity: int = 50) -> dict:
    """민감도 0(둔함)~100(예민) → 경계/폭 임계값. 50 ≈ 이전 동작 기준."""
    s = max(0, min(100, int(sensitivity))) / 100.0
    return {
        "edge_k": round(8.0 - 5.0 * s, 2),          # 8.0 → 3.0
        "edge_min": round(4.0 - 3.0 * s, 2),        # 4.0 → 1.0 px
        "width_ratio": round(0.35 - 0.23 * s, 3),   # 0.35 → 0.12
        "gap_ratio": round(0.022 - 0.017 * s, 4),   # 0.022 → 0.005
    }


def _edge_threshold(d: np.ndarray, edge_k: float, edge_min: float) -> float:
    """단 경계는 diff를 크게 만듦 → 하위 분위만으로 '노이즈' 추정 후 임계값 계산."""
    if d.size == 0:
        return float(edge_min)
    cut = float(np.percentile(d, 65))
    noise = d[d <= cut]
    if noise.size < 5:
        noise = d
    med = float(np.median(noise))
    mad = float(np.median(np.abs(noise - med)))
    sigma = max(mad * 1.4826, 0.25)
    return max(float(edge_min), med + float(edge_k) * sigma)


def auto_segment_steps(
    points: list,
    min_width: int = 0,
    smooth: int = 5,
    edge_k: float = 4.0,
    edge_min: float = 2.0,
    width_ratio: float = 0.22,
    gap_ratio: float = 0.012,
    sensitivity: Optional[int] = None,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """계단 수를 모른 채, 프로파일에서 '평탄 구간(단)'을 자동으로 찾는다.

    y가 평평한 구간 = 한 단, y가 크게 튀는 곳 = 단 경계.
    sensitivity(0~100): 단 경계 검출 민감도 (높을수록 작은 단차도 분리).
    min_width<=0 이면 구간 폭 분포에서 자동으로 기준을 정한다(수동 입력 불필요).
    반환: [{"mean_x", "y_pixel"(중앙값), "count"}, ...] (x오름차순)
    """
    if sensitivity is not None:
        p = _step_detect_params(sensitivity)
        edge_k = p["edge_k"]
        edge_min = p["edge_min"]
        width_ratio = p["width_ratio"]
        gap_ratio = p["gap_ratio"]

    pts = sorted([p for p in (points or []) if p is not None], key=lambda p: p[0])
    if len(pts) < 20:
        return None, "레이저 점이 너무 적습니다 (검출/범위 확인)"

    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)
    ys_s = _medfilt1d(ys, smooth)

    d = np.abs(np.diff(ys_s))
    thr = _edge_threshold(d, edge_k, edge_min)

    total_extent = float(xs[-1] - xs[0]) if xs.size > 1 else 0.0
    gap_thr = max(4.0, float(gap_ratio) * total_extent)

    bounds = [0]
    for i in range(d.size):
        if d[i] > thr or (xs[i + 1] - xs[i]) > gap_thr:
            bounds.append(i + 1)
    bounds.append(len(xs))

    # 1차: 모든 후보 구간 수집
    raw = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        sx = xs[a:b]
        sy = ys[a:b]
        if sx.size == 0:
            continue
        raw.append((sx, sy, float(sx[-1] - sx[0])))
    if not raw:
        return None, "평탄 구간(단)을 찾지 못했습니다"

    # 최소 단 폭 자동 결정 (평탄 단은 넓고 경사는 좁음)
    if min_width and int(min_width) > 0:
        min_w = float(min_width)
    else:
        widths = np.array([w for (_, _, w) in raw], dtype=np.float64)
        min_w = max(6.0, float(width_ratio) * float(np.median(widths)))

    segs = []
    for sx, sy, width in raw:
        if width < min_w or sx.size < max(3, int(min_w) // 2):
            continue  # 폭이 좁으면 단 사이 경사(riser) → 버림
        segs.append(
            {
                "mean_x": round(float(sx.mean()), 1),
                "y_pixel": round(float(np.median(sy)), 3),
                "count": int(sx.size),
            }
        )

    if len(segs) < 1:
        return None, "평탄 구간(단)을 찾지 못했습니다 (검출 확인)"
    return segs, None


def build_lut_auto(
    points: list,
    increment_mm: float,
    base_mm: float = 0.0,
    reverse_order: bool = False,
    min_width: int = 0,
    sensitivity: int = 50,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """자동 검출된 평탄 구간에 base + i*increment 높이를 순서대로 매겨 LUT 생성.

    계단 '개수'는 받지 않고 데이터에서 찾는다. 증가량(물리 스펙)만 받는다.
    """
    segs, err = None, None
    for sens in sorted(set([sensitivity, min(100, sensitivity + 20), min(100, sensitivity + 40), 100])):
        segs, err = auto_segment_steps(points, min_width=min_width, sensitivity=sens)
        if err:
            continue
        if len(segs) >= 2:
            break
    if err and (segs is None or len(segs) < 2):
        return None, err
    if segs is None or len(segs) < 2:
        return None, "단을 2개 이상 찾지 못했습니다 (레이저 선·계단 전체가 화면에 들어오는지 확인)"
    segs.sort(key=lambda s: s["mean_x"], reverse=reverse_order)
    table = []
    for i, s in enumerate(segs):
        table.append(
            {
                "y_pixel": s["y_pixel"],
                "height_mm": round(base_mm + i * increment_mm, 4),
                "mean_x": s["mean_x"],
                "count": s["count"],
            }
        )
    return table, None


def cluster_steps(
    points: list, n_steps: int, reverse_order: bool = False
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """점들을 y값으로 n_steps개 단으로 군집화하고 x순서로 정렬.

    반환: [{"mean_x", "y_pixel"(중앙값), "count"}, ...]
    """
    pts = [p for p in (points or []) if p is not None]
    if len(pts) < int(n_steps) * 2:
        return None, "레이저 점이 너무 적습니다 (점을 너무 많이 지웠거나 검출 실패)"

    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float32)
    data = ys.reshape(-1, 1).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    _compact, labels, _centers = cv2.kmeans(
        data, int(n_steps), None, criteria, 5, cv2.KMEANS_PP_CENTERS
    )
    labels = labels.flatten()

    clusters = []
    for k in range(int(n_steps)):
        idx = labels == k
        if not np.any(idx):
            continue
        clusters.append(
            {
                "mean_x": round(float(xs[idx].mean()), 1),
                "y_pixel": round(float(np.median(ys[idx])), 3),
                "count": int(idx.sum()),
            }
        )
    if len(clusters) < 2:
        return None, "단(계단)을 충분히 구분하지 못했습니다"

    clusters.sort(key=lambda c: c["mean_x"], reverse=reverse_order)
    return clusters, None


def _lut_path(calib_dir: str, camera_id: int) -> str:
    return os.path.join(calib_dir, f"camera_{camera_id}_lut.json")


def save_lut(calib_dir: str, camera_id: int, table: List[dict], meta: dict) -> str:
    os.makedirs(calib_dir, exist_ok=True)
    path = _lut_path(calib_dir, camera_id)
    payload = {
        "camera_id": camera_id,
        "created_at": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "table": table,
        **meta,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def load_lut(calib_dir: str, camera_id: int) -> Optional[dict]:
    path = _lut_path(calib_dir, camera_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def y_to_height(lut: dict, y: float) -> Optional[float]:
    """LUT 표(y_pixel↔height_mm)를 선형 보간/외삽해 y → 높이(mm).

    LUT는 캘리브레이션 시점 y 범위를 저장한다. 측정 y가 범위를 벗어나도
    양 끝 구간 기울기로 외삽한다(예전처럼 0mm로 고정하지 않음).
    """
    table = lut.get("table") or []
    if len(table) < 2 or y is None or np.isnan(y):
        return None
    ys = np.array([t["y_pixel"] for t in table], dtype=np.float64)
    hs = np.array([t["height_mm"] for t in table], dtype=np.float64)
    order = np.argsort(ys)
    ys = ys[order]
    hs = hs[order]
    yf = float(y)
    if yf <= ys[0]:
        slope = (hs[1] - hs[0]) / max(ys[1] - ys[0], 1e-9)
        return float(hs[0] + slope * (yf - ys[0]))
    if yf >= ys[-1]:
        slope = (hs[-1] - hs[-2]) / max(ys[-1] - ys[-2], 1e-9)
        return float(hs[-1] + slope * (yf - ys[-1]))
    return float(np.interp(yf, ys, hs))


def lut_y_range(lut: dict) -> Optional[dict]:
    table = lut.get("table") or []
    if len(table) < 2:
        return None
    ys = [t["y_pixel"] for t in table]
    hs = [t["height_mm"] for t in table]
    return {"y_min": min(ys), "y_max": max(ys), "h_min": min(hs), "h_max": max(hs)}


def region_mean_y(profile: np.ndarray, x0: int, x1: int) -> Optional[float]:
    x0, x1 = sorted((int(x0), int(x1)))
    x0 = max(0, x0)
    x1 = min(len(profile) - 1, x1)
    if x1 <= x0:
        return None
    seg = profile[x0 : x1 + 1]
    valid = seg[~np.isnan(seg)]
    if valid.size == 0:
        return None
    return float(np.median(valid))
