"""
라인 레이저 기반 높이(단차)·간격 측정 유틸.

파이프라인:
  왜곡보정 이미지 → 파란 레이저 선 검출(프로파일: x→y) →
  [계단블록] 프로파일을 단(plateau)으로 분할 → LUT(y_pixel→height_mm) 생성/저장 →
  [단차] 두 구간 대표 y → LUT 보간 → 단차 = height_A − height_B
  [간격] 끊김 보존 검출 → 직선 세그먼트 끝점 피팅 → gap_px (× mm/px → mm)
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime
from typing import List, Optional, Tuple

import cv2
import numpy as np

SUBPIXEL_MODES = ("com", "gaussian")
DEFAULT_SUBPIXEL_MODE = "gaussian"
DEFAULT_MIN_LASER_SNR = 2.0
DEFAULT_MIN_LINE_WIDTH_PX = 1.0
DEFAULT_MAX_LINE_WIDTH_PX = 30.0
DEFAULT_MAX_GAUSS_RMSE = 0.45
DEFAULT_DENOISE = True
DEFAULT_DENOISE_MAD_K = 3.5
DEFAULT_DENOISE_MIN_RUN = 5  # 이보다 짧은 연속 구간은 노이즈로 제거


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


def _reject_outliers_mad(
    profile: np.ndarray, mad_k: float = DEFAULT_DENOISE_MAD_K, win: int = 21
) -> np.ndarray:
    """국소 median + MAD로 스파이크를 NaN 제거 (값을 바꾸지 않음)."""
    if profile is None or len(profile) == 0:
        return profile
    k = float(mad_k or 0)
    if k <= 0:
        return profile
    w = int(win) | 1
    r = w // 2
    out = profile.copy().astype(np.float64)
    n = len(out)
    for x in range(n):
        y0 = out[x]
        if np.isnan(y0):
            continue
        lo = max(0, x - r)
        hi = min(n, x + r + 1)
        neigh = out[lo:hi]
        neigh = neigh[~np.isnan(neigh)]
        if neigh.size < 5:
            continue
        med = float(np.median(neigh))
        mad = float(np.median(np.abs(neigh - med)))
        sigma = max(mad * 1.4826, 0.35)
        if abs(float(y0) - med) > k * sigma:
            out[x] = np.nan
    return out


def _remove_short_runs(
    profile: np.ndarray, min_run: int = DEFAULT_DENOISE_MIN_RUN
) -> np.ndarray:
    """짧은 연속 유효 구간(고립 점 덩어리)을 제거."""
    if profile is None or len(profile) == 0:
        return profile
    min_run = int(min_run or 0)
    if min_run <= 1:
        return profile
    out = profile.copy()
    n = len(out)
    i = 0
    while i < n:
        if np.isnan(out[i]):
            i += 1
            continue
        j = i + 1
        while j < n and not np.isnan(out[j]):
            j += 1
        if (j - i) < min_run:
            out[i:j] = np.nan
        i = j
    return out


def denoise_laser_profile(
    profile: np.ndarray,
    max_jump: float = 25.0,
    mad_k: float = DEFAULT_DENOISE_MAD_K,
    min_run: int = DEFAULT_DENOISE_MIN_RUN,
    enabled: bool = True,
) -> np.ndarray:
    """레이저 프로파일 노이즈 제거 (스무딩 없음 — 이상점만 NaN으로 삭제).

    1) 연속성 점프 제거
    2) 국소 MAD 스파이크 제거
    3) 짧은 고립 구간 제거
    """
    if profile is None or not enabled:
        return profile
    out = _reject_outliers_continuity(profile, float(max_jump))
    out = _reject_outliers_mad(out, mad_k=float(mad_k))
    out = _remove_short_runs(out, min_run=int(min_run))
    return out


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


def _com_subpixel_y(y_idx: np.ndarray, intensity: np.ndarray) -> float:
    total = float(intensity.sum())
    if total <= 0:
        return np.nan
    return float((y_idx * intensity).sum() / total)


def _gaussian_subpixel_y(
    y_idx: np.ndarray,
    intensity: np.ndarray,
    min_points: int = 5,
) -> float:
    """Gaussian peak y: ln(I) 2차 다항식 피팅 → mu = -b/(2a). 실패 시 COM 폴백."""
    if y_idx.size == 0 or intensity.size == 0:
        return np.nan

    total = float(intensity.sum())
    if total <= 0:
        return np.nan

    if y_idx.size < min_points:
        return _com_subpixel_y(y_idx, intensity)

    bg = float(np.min(intensity))
    signal = intensity.astype(np.float64) - bg
    pos = signal > 1e-6
    if int(pos.sum()) < min_points:
        return _com_subpixel_y(y_idx, intensity)

    ys = y_idx[pos]
    sig = signal[pos]
    log_i = np.log(sig)

    try:
        a, b, _c = np.polyfit(ys, log_i, 2)
    except (np.linalg.LinAlgError, ValueError):
        return _com_subpixel_y(y_idx, intensity)

    if a >= -1e-12:
        return _com_subpixel_y(y_idx, intensity)

    mu = -b / (2.0 * a)
    y_min, y_max = float(y_idx[0]), float(y_idx[-1])
    if mu < y_min - 0.5 or mu > y_max + 0.5:
        return _com_subpixel_y(y_idx, intensity)
    return float(mu)


def _line_quality(y_idx: np.ndarray, intensity: np.ndarray) -> dict:
    """열 단위 레이저 후보 품질: SNR, FWHM 근사 폭, 포화 비율."""
    if y_idx.size == 0 or intensity.size == 0:
        return {"snr": 0.0, "width_px": 0.0, "saturated_ratio": 0.0}

    values = intensity.astype(np.float64)
    bg = float(np.min(values))
    signal = values - bg
    peak_signal = float(np.max(signal)) if signal.size else 0.0
    if peak_signal <= 0:
        return {"snr": 0.0, "width_px": 0.0, "saturated_ratio": 0.0}

    low = signal[signal <= np.percentile(signal, 50)]
    noise = float(np.std(low)) if low.size >= 3 else 0.0
    snr = peak_signal / max(noise, 1.0)

    half_peak = peak_signal * 0.5
    above_half = np.where(signal >= half_peak)[0]
    if above_half.size:
        width_px = float(y_idx[above_half[-1]] - y_idx[above_half[0]] + 1.0)
    else:
        width_px = 0.0

    saturated_ratio = float(np.count_nonzero(values >= 254.0) / max(1, values.size))
    return {
        "snr": float(snr),
        "width_px": width_px,
        "saturated_ratio": saturated_ratio,
    }


def _gaussian_fit_result(y_idx: np.ndarray, intensity: np.ndarray, min_points: int = 5) -> dict:
    """Gaussian fit 결과와 품질. 실패 시 y는 COM fallback."""
    fallback_y = _com_subpixel_y(y_idx, intensity)
    result = {
        "y": fallback_y,
        "mode_used": "com",
        "sigma_px": None,
        "fwhm_px": None,
        "rmse": None,
        "r2": None,
        "fallback_reason": None,
    }

    if y_idx.size < min_points or intensity.size < min_points:
        result["fallback_reason"] = "few_points"
        return result

    bg = float(np.min(intensity))
    signal = intensity.astype(np.float64) - bg
    pos = signal > 1e-6
    if int(pos.sum()) < min_points:
        result["fallback_reason"] = "low_signal"
        return result

    ys = y_idx[pos]
    sig = signal[pos]
    log_i = np.log(sig)

    try:
        a, b, c = np.polyfit(ys, log_i, 2)
    except (np.linalg.LinAlgError, ValueError):
        result["fallback_reason"] = "fit_error"
        return result

    if a >= -1e-12:
        result["fallback_reason"] = "not_gaussian"
        return result

    mu = float(-b / (2.0 * a))
    y_min, y_max = float(y_idx[0]), float(y_idx[-1])
    if mu < y_min - 0.5 or mu > y_max + 0.5:
        result["fallback_reason"] = "peak_outside"
        return result

    pred = a * ys * ys + b * ys + c
    residual = log_i - pred
    rmse = float(np.sqrt(np.mean(residual * residual)))
    ss_res = float(np.sum(residual * residual))
    ss_tot = float(np.sum((log_i - float(np.mean(log_i))) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 1.0
    sigma = float(np.sqrt(-1.0 / (2.0 * a)))
    fwhm = float(2.354820045 * sigma)

    result.update(
        {
            "y": mu,
            "mode_used": "gaussian",
            "sigma_px": sigma,
            "fwhm_px": fwhm,
            "rmse": rmse,
            "r2": float(r2),
            "fallback_reason": None,
        }
    )
    return result


def _subpixel_y(
    y_idx: np.ndarray,
    intensity: np.ndarray,
    subpixel_mode: str,
) -> float:
    mode = (subpixel_mode or DEFAULT_SUBPIXEL_MODE).lower()
    if mode not in SUBPIXEL_MODES:
        mode = DEFAULT_SUBPIXEL_MODE
    if mode == "com":
        return _com_subpixel_y(y_idx, intensity)
    return _gaussian_subpixel_y(y_idx, intensity)


def _compute_profile_from_weight(
    weight: np.ndarray,
    peak_band: int,
    min_col_weight: float,
    subpixel_mode: str,
    min_snr: float = DEFAULT_MIN_LASER_SNR,
    min_line_width_px: float = DEFAULT_MIN_LINE_WIDTH_PX,
    max_line_width_px: float = DEFAULT_MAX_LINE_WIDTH_PX,
    max_gauss_rmse: float = DEFAULT_MAX_GAUSS_RMSE,
) -> Tuple[np.ndarray, dict]:
    """각 x열 서브픽셀 y 프로파일."""
    h, w = weight.shape
    col_sum = weight.sum(axis=0)
    profile = np.full(w, np.nan, dtype=np.float64)
    quality = {
        "candidate_columns": int(np.count_nonzero(col_sum > float(min_col_weight))),
        "valid_columns_before_continuity": 0,
        "rejected_low_snr": 0,
        "rejected_width": 0,
        "gaussian_used": 0,
        "gaussian_fallback": 0,
        "snr_values": [],
        "width_values": [],
        "gaussian_rmse_values": [],
        "saturated_columns": 0,
    }
    mode = (subpixel_mode or DEFAULT_SUBPIXEL_MODE).lower()
    if mode not in SUBPIXEL_MODES:
        mode = DEFAULT_SUBPIXEL_MODE

    band = int(peak_band)
    min_w = float(min_col_weight)

    for x in range(w):
        if col_sum[x] <= min_w:
            continue
        col = weight[:, x]
        if band > 0:
            pk = int(np.argmax(col))
            y0 = max(0, pk - band)
            y1 = min(h, pk + band + 1)
        else:
            y0, y1 = 0, h
        ys = np.arange(y0, y1, dtype=np.float64)
        seg = col[y0:y1]
        if seg.sum() <= 0:
            continue
        line_q = _line_quality(ys, seg)
        snr = float(line_q["snr"])
        width_px = float(line_q["width_px"])
        quality["snr_values"].append(snr)
        quality["width_values"].append(width_px)
        if line_q["saturated_ratio"] > 0:
            quality["saturated_columns"] += 1

        if min_snr > 0 and snr < float(min_snr):
            quality["rejected_low_snr"] += 1
            continue
        if (
            width_px < float(min_line_width_px)
            or (max_line_width_px > 0 and width_px > float(max_line_width_px))
        ):
            quality["rejected_width"] += 1
            continue

        if mode == "com":
            profile[x] = _com_subpixel_y(ys, seg)
            quality["valid_columns_before_continuity"] += 1
            continue

        fit = _gaussian_fit_result(ys, seg)
        rmse = fit.get("rmse")
        if rmse is not None:
            quality["gaussian_rmse_values"].append(float(rmse))
        if (
            fit.get("mode_used") == "gaussian"
            and rmse is not None
            and rmse <= float(max_gauss_rmse)
        ):
            profile[x] = float(fit["y"])
            quality["gaussian_used"] += 1
        else:
            profile[x] = _com_subpixel_y(ys, seg)
            quality["gaussian_fallback"] += 1
        quality["valid_columns_before_continuity"] += 1

    return profile, quality


def _compute_profile_tracked(
    weight: np.ndarray,
    peak_band: int,
    min_col_weight: float,
    subpixel_mode: str,
    min_snr: float = DEFAULT_MIN_LASER_SNR,
    min_line_width_px: float = DEFAULT_MIN_LINE_WIDTH_PX,
    max_line_width_px: float = DEFAULT_MAX_LINE_WIDTH_PX,
    max_gauss_rmse: float = DEFAULT_MAX_GAUSS_RMSE,
    track_band: int = 10,
) -> Tuple[np.ndarray, dict]:
    """열별 서브픽셀 y — 이전 열 y 근처를 우선 탐색해 프로파일을 일자에 가깝게 유지.

    계단 단 경계(큰 y 점프)에서는 국소 신호가 약해지면 전역 peak로 전환한다.
    """
    h, w = weight.shape
    col_sum = weight.sum(axis=0)
    profile = np.full(w, np.nan, dtype=np.float64)
    quality = {
        "candidate_columns": int(np.count_nonzero(col_sum > float(min_col_weight))),
        "valid_columns_before_continuity": 0,
        "rejected_low_snr": 0,
        "rejected_width": 0,
        "gaussian_used": 0,
        "gaussian_fallback": 0,
        "tracked_columns": 0,
        "global_peak_columns": 0,
        "snr_values": [],
        "width_values": [],
        "gaussian_rmse_values": [],
        "saturated_columns": 0,
    }
    mode = (subpixel_mode or DEFAULT_SUBPIXEL_MODE).lower()
    if mode not in SUBPIXEL_MODES:
        mode = DEFAULT_SUBPIXEL_MODE

    band = max(2, int(peak_band))
    tb = max(2, int(track_band))
    min_w = float(min_col_weight)
    prev_y: Optional[float] = None
    gap_run = 0

    def _subpixel(ys: np.ndarray, seg: np.ndarray) -> Tuple[float, dict]:
        line_q = _line_quality(ys, seg)
        if mode == "com":
            return _com_subpixel_y(ys, seg), {"mode": "com", "rmse": None, **line_q}
        fit = _gaussian_fit_result(ys, seg)
        rmse = fit.get("rmse")
        if (
            fit.get("mode_used") == "gaussian"
            and rmse is not None
            and rmse <= float(max_gauss_rmse)
        ):
            return float(fit["y"]), {"mode": "gaussian", "rmse": rmse, **line_q}
        return _com_subpixel_y(ys, seg), {"mode": "com_fallback", "rmse": rmse, **line_q}

    for x in range(w):
        if col_sum[x] <= min_w:
            gap_run += 1
            if gap_run > 15:
                prev_y = None
            continue
        gap_run = 0
        col = weight[:, x]

        used_track = False
        if prev_y is not None:
            cy = int(round(prev_y))
            y0 = max(0, cy - tb)
            y1 = min(h, cy + tb + 1)
            local = col[y0:y1]
            # 이전 y 근처에 충분한 에너지가 있으면 추적 유지 (plateau 안정화)
            if float(local.sum()) >= min_w * 0.25 and float(np.max(local)) > 0:
                pk_local = int(np.argmax(local)) + y0
                y0b = max(0, pk_local - band)
                y1b = min(h, pk_local + band + 1)
                ys = np.arange(y0b, y1b, dtype=np.float64)
                seg = col[y0b:y1b]
                used_track = True
            else:
                ys = seg = None
        else:
            ys = seg = None

        if not used_track:
            pk = int(np.argmax(col))
            y0b = max(0, pk - band)
            y1b = min(h, pk + band + 1)
            ys = np.arange(y0b, y1b, dtype=np.float64)
            seg = col[y0b:y1b]
            quality["global_peak_columns"] += 1
        else:
            quality["tracked_columns"] += 1

        if seg is None or float(seg.sum()) <= 0:
            continue

        y_val, meta = _subpixel(ys, seg)
        snr = float(meta.get("snr") or 0.0)
        width_px = float(meta.get("width_px") or 0.0)
        quality["snr_values"].append(snr)
        quality["width_values"].append(width_px)
        if float(meta.get("saturated_ratio") or 0) > 0:
            quality["saturated_columns"] += 1
        if min_snr > 0 and snr < float(min_snr):
            quality["rejected_low_snr"] += 1
            continue
        if width_px < float(min_line_width_px) or (
            max_line_width_px > 0 and width_px > float(max_line_width_px)
        ):
            quality["rejected_width"] += 1
            continue
        if meta.get("mode") == "gaussian":
            quality["gaussian_used"] += 1
            if meta.get("rmse") is not None:
                quality["gaussian_rmse_values"].append(float(meta["rmse"]))
        else:
            quality["gaussian_fallback"] += 1
            if meta.get("rmse") is not None:
                quality["gaussian_rmse_values"].append(float(meta["rmse"]))

        profile[x] = float(y_val)
        prev_y = float(y_val)
        quality["valid_columns_before_continuity"] += 1

    return profile, quality


def refine_lut_profile(
    profile: np.ndarray,
    max_hole: int = 8,
    smooth: int = 7,
    mad_k: float = 3.5,
    min_run: int = 5,
) -> np.ndarray:
    """LUT용 프로파일 가벼운 정제: 짧은 구멍 메움 + median (검출율 유지 우선)."""
    if profile is None or len(profile) == 0:
        return profile
    out = profile.astype(np.float64).copy()
    w = len(out)
    valid = ~np.isnan(out)

    mb = max(0, int(max_hole))
    if mb > 0:
        i = 0
        while i < w:
            if valid[i]:
                i += 1
                continue
            j = i
            while j < w and not valid[j]:
                j += 1
            hole = j - i
            if 0 < hole <= mb and i > 0 and j < w and valid[i - 1] and valid[j]:
                y0, y1 = float(out[i - 1]), float(out[j])
                for k in range(i, j):
                    t = (k - i + 1) / (hole + 1)
                    out[k] = y0 * (1.0 - t) + y1 * t
                valid[i:j] = True
            i = j

    if int(np.count_nonzero(valid)) >= 5:
        filled = out.copy()
        last = float(np.nanmedian(out[valid]))
        for x in range(w):
            if np.isnan(filled[x]):
                filled[x] = last
            else:
                last = float(filled[x])
        sm = _medfilt1d(filled, int(smooth) | 1)
        out = np.where(valid, sm, out)

    out = denoise_laser_profile(
        out,
        max_jump=30.0,
        mad_k=float(mad_k),
        min_run=int(min_run),
        enabled=True,
    )
    return out


def detect_laser_profile_for_lut(
    undistorted_bgr: np.ndarray,
    **kwargs,
):
    """LUT용: 강건 자동 검출 후 동일 높이의 짧은 누락만 복원."""
    kwargs = dict(kwargs)
    kwargs["preserve_gaps"] = False
    return detect_laser_profile(undistorted_bgr, **kwargs)


def _summarize_detection_quality(quality: dict, width: int, valid_after: int) -> dict:
    def _mean(values):
        return round(float(np.mean(values)), 3) if values else None

    def _percentile(values, p):
        return round(float(np.percentile(values, p)), 3) if values else None

    candidate = int(quality.get("candidate_columns") or 0)
    valid_before = int(quality.get("valid_columns_before_continuity") or 0)
    return {
        "candidate_columns": candidate,
        "valid_before_continuity": valid_before,
        "valid_after_continuity": int(valid_after),
        "coverage": round(int(valid_after) / max(1, int(width)), 3),
        "candidate_accept_ratio": round(valid_before / max(1, candidate), 3),
        "rejected_low_snr": int(quality.get("rejected_low_snr") or 0),
        "rejected_width": int(quality.get("rejected_width") or 0),
        "gaussian_used": int(quality.get("gaussian_used") or 0),
        "gaussian_fallback": int(quality.get("gaussian_fallback") or 0),
        "mean_snr": _mean(quality.get("snr_values") or []),
        "p10_snr": _percentile(quality.get("snr_values") or [], 10),
        "mean_width_px": _mean(quality.get("width_values") or []),
        "p90_width_px": _percentile(quality.get("width_values") or [], 90),
        "mean_gauss_rmse": _mean(quality.get("gaussian_rmse_values") or []),
        "saturated_columns": int(quality.get("saturated_columns") or 0),
    }


def _robust_laser_response(
    undistorted_bgr: np.ndarray, laser_color: str = "blue"
) -> np.ndarray:
    """레이저 색 우세도와 수직 top-hat을 결합한 얇은 수평 레이저 응답.

    laser_color="blue"|"red". 파란/빨간 레이저 모두 중심이 흰색으로 포화되므로
    색 채널만 교체하면 동일 파이프라인으로 검출된다.
    """
    color = (laser_color or "blue").lower()
    bgr = undistorted_bgr.astype(np.float32)
    b, g, r = cv2.split(bgr)

    if color == "red":
        main = r                       # 레이저 우세 채널
        other = 0.5 * (g + b)
        other_max = np.maximum(g, b)
        main8 = undistorted_bgr[:, :, 2]
    else:
        main = b
        other = 0.5 * (g + r)
        other_max = np.maximum(g, r)
        main8 = undistorted_bgr[:, :, 0]

    # 넓은 유색 물체 자체가 응답이 되지 않도록 색상 성분에도 수직 top-hat을 적용한다.
    chroma = np.maximum(main - other, 0.0)
    dominance = np.maximum(main - other_max, 0.0)

    # 커널이 레이저 두께(bloom 포함, 포화 시 ~190px 실측)보다 작으면
    # top-hat 응답이 0이 되어 두꺼운 레이저가 통째로 사라진다.
    kernel_h = max(151, (undistorted_bgr.shape[0] // 20) | 1)
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_h))
    chroma_line = cv2.morphologyEx(
        np.clip(chroma, 0, 255).astype(np.uint8), cv2.MORPH_TOPHAT, vertical_kernel
    ).astype(np.float32)
    dominance_line = cv2.morphologyEx(
        np.clip(dominance, 0, 255).astype(np.uint8), cv2.MORPH_TOPHAT, vertical_kernel
    ).astype(np.float32)
    local_line = cv2.morphologyEx(
        main8, cv2.MORPH_TOPHAT, vertical_kernel
    ).astype(np.float32)

    response = 0.55 * chroma_line + 0.25 * dominance_line + 0.40 * local_line
    response *= np.clip((main - 8.0) / 64.0, 0.0, 1.0)

    # 포화 코어(우세채널>=250)는 top-hat과 무관하게 직접 응답 — 커널보다 두꺼워진
    # 포화 레이저도 놓치지 않는다 (덩어리 오검출은 컴포넌트 필터가 방어).
    sat = (main8 >= 250).astype(np.float32) * 255.0
    response = np.maximum(response, sat)

    return cv2.GaussianBlur(response, (1, 3), 0)


def _robust_blue_response(undistorted_bgr: np.ndarray) -> np.ndarray:
    """하위호환 래퍼 — 파란 레이저 응답."""
    return _robust_laser_response(undistorted_bgr, "blue")


def _automatic_response_mask(response: np.ndarray) -> Tuple[np.ndarray, float]:
    """희소한 레이저 응답에서 장면별 임계값을 자동 결정."""
    finite = response[np.isfinite(response)]
    if finite.size == 0 or float(np.max(finite)) <= 0:
        return np.zeros(response.shape, dtype=np.uint8), 0.0

    scale = 255.0 / max(float(np.percentile(finite, 99.95)), 1.0)
    response_u8 = np.clip(response * scale, 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(
        response_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    positive = finite[finite > 0]
    p90 = float(np.percentile(positive, 90)) if positive.size else 0.0
    threshold = max(4.0, float(otsu) / scale * 0.72, p90 * 0.35)
    mask = np.where(response >= threshold, 255, 0).astype(np.uint8)

    # 수평 방향 opening으로 점/세로 반사를 제거하고, 짧은 광량 누락만 연결한다.
    open_w = max(11, min(25, (response.shape[1] // 300) | 1))
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (open_w, 1))
    )
    close_w = max(7, min(31, (response.shape[1] // 240) | 1))
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (close_w, 1))
    )
    return mask, threshold


def _keep_line_like_components(
    mask: np.ndarray,
    response: np.ndarray,
    intensity: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, int]:
    """가로로 긴 선형 연결요소만 남긴다 (bloom 두께는 허용, 반사 덩어리·점은 제거).

    두께로 자르면 굵은 레이저가 통째로 탈락하므로, '가로 폭 대비 세로 높이'
    (aspect ratio)로 선/덩어리를 구분한다. 코어 중앙값은 열별 추출에서 계산한다.
    """
    h, w = mask.shape
    # 세로로 끊긴 bloom을 살짝 이어 하나의 선으로 만든다.
    bridged = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (21, 3))
    )
    num, labels, stats, _ = cv2.connectedComponentsWithStats(bridged, 8)
    keep = np.zeros_like(mask)
    min_width = max(40, int(round(w * 0.02)))
    max_height = max(60, int(h * 0.12))  # bloom 포함 허용 (포화 레이저 bloom ~220px 실측)
    guide = intensity if intensity is not None else response
    candidates = []

    for i in range(1, num):
        x, y, cw, ch, area = stats[i]
        if cw < min_width:
            continue
        if y >= int(h * 0.978):
            continue
        # 선형성: bbox 높이 대신 '컬럼별 두께 중앙값'으로 판정.
        # 박스 코너의 국소 세로 flare가 bbox 높이를 부풀려 진짜 레이저가
        # 통째로 기각되던 문제를 막는다(반사 덩어리는 두께 중앙값도 커서 여전히 기각).
        comp = labels[y:y + ch, x:x + cw] == i
        col_counts = comp.sum(axis=0)
        col_counts = col_counts[col_counts > 0]
        med_h = float(np.median(col_counts)) if col_counts.size else float(ch)
        if cw < med_h * 3:
            continue
        if med_h > max_height:
            continue
        pixels = guide[labels == i]
        strength = float(np.median(pixels)) if pixels.size else 0.0
        if strength <= 0:
            continue
        candidates.append((float(cw) * strength, i, x, y, cw, ch))

    if not candidates:
        return keep, 0

    # 우측 왜곡 경계에 세로로 흩어진 선형 artifact 제거
    right_edge = [c for c in candidates if c[2] >= int(w * 0.85)]
    if len(right_edge) >= 8:
        edge_y0 = min(c[3] for c in right_edge)
        edge_y1 = max(c[3] + c[5] for c in right_edge)
        if edge_y1 - edge_y0 >= int(h * 0.15):
            candidates = [c for c in candidates if c[2] < int(w * 0.85)]
    if not candidates:
        return keep, 0

    candidates.sort(reverse=True)
    best_score = candidates[0][0]
    kept = 0
    for score, i, _x, _y, _cw, _ch in candidates:
        # 가장 강한 선 대비 너무 약한 조각은 버림 (단, 상위 몇 개는 유지)
        if score < best_score * 0.05 and kept >= 3:
            continue
        # 원본 mask 픽셀만 남긴다 (bridge로 늘린 영역 제외)
        keep[(labels == i) & (mask > 0)] = 255
        kept += 1
    return keep, kept


def _bright_band_center(
    col: np.ndarray, anchor: int, max_span: int = 150
) -> Tuple[float, float, float]:
    """기준점 주변에서 '연속된 밝은 띠 전체'의 중점을 서브픽셀로 계산.

    흰색 과포화 코어를 밝은 띠로 보고, 그 띠의 위·아래 가장자리를 임계 교차로
    구해 정중앙을 반환한다(= 굵은 레이저의 중간값). 임계를 피크의 75%로 잡아
    코어보다 어두운 파란 bloom(글로우)은 제외한다 — bloom이 위아래 비대칭이라
    낮은 임계에서는 중심이 bloom 쪽으로 출렁였다.
    """
    n = col.size
    if n == 0:
        return np.nan, 0.0, 0.0
    a = int(max(0, min(n - 1, anchor)))
    w0 = max(0, a - max_span)
    w1 = min(n, a + max_span + 1)
    peak = float(np.max(col[w0:w1]))
    if peak <= 0:
        return np.nan, 0.0, 0.0
    # 포화 코어는 포함하고 bloom·배경은 제외하는 임계
    thr = max(0.75 * peak, 90.0)
    # 기준점이 어두우면 창 내 최대 밝기 위치로 스냅
    if col[a] < thr:
        a = w0 + int(np.argmax(col[w0:w1]))

    lo = a
    while lo - 1 >= w0 and col[lo - 1] >= thr:
        lo -= 1
    hi = a
    while hi + 1 < w1 and col[hi + 1] >= thr:
        hi += 1

    y_lo = float(lo)
    if lo - 1 >= 0:
        v0, v1 = float(col[lo - 1]), float(col[lo])
        if v1 > v0:
            y_lo = (lo - 1) + (thr - v0) / (v1 - v0)
    y_hi = float(hi)
    if hi + 1 < n:
        v0, v1 = float(col[hi]), float(col[hi + 1])
        if v0 > v1:
            y_hi = hi + (v0 - thr) / (v0 - v1)

    center = 0.5 * (y_lo + y_hi)
    width = max(1.0, y_hi - y_lo + 1.0)
    return center, peak, width


def _extract_subpixel_profile(
    intensity: np.ndarray, mask: np.ndarray
) -> Tuple[np.ndarray, list, list]:
    """각 열에서 밝은 띠 전체의 중점(굵은 레이저의 중간값)을 계산 (x방향 추적)."""
    h, w = mask.shape
    profile = np.full(w, np.nan, dtype=np.float64)
    strengths = []
    widths = []
    prev_y: Optional[float] = None
    gap_run = 0
    for x in range(w):
        ys = np.flatnonzero(mask[:, x])
        if ys.size == 0:
            gap_run += 1
            if gap_run > 20:
                prev_y = None
            continue
        gap_run = 0

        col = intensity[:, x].astype(np.float64)
        # 마스크(파란 응답) 위치를 기준점으로 삼되, 이전 열 근처에 마스크가 있으면
        # 그쪽을 우선해 실제 단차가 아닌 이중선 점프를 막는다.
        anchor = int(round(float(np.median(ys))))
        if prev_y is not None and np.isfinite(prev_y):
            near = ys[np.abs(ys.astype(np.float64) - float(prev_y)) <= 12.0]
            if near.size:
                anchor = int(round(float(np.median(near))))

        y_val, strength, width_px = _bright_band_center(col, anchor)
        if np.isnan(y_val):
            continue

        # 큰 점프가 났는데 이전 위치 근처에도 밝은 띠가 있으면 그쪽을 우선
        if prev_y is not None and abs(float(y_val) - float(prev_y)) > 16.0:
            near = ys[np.abs(ys.astype(np.float64) - float(prev_y)) <= 12.0]
            if near.size:
                a2 = int(round(float(np.median(near))))
                y_retry, s2, w2 = _bright_band_center(col, a2)
                if not np.isnan(y_retry) and abs(float(y_retry) - float(prev_y)) < abs(
                    float(y_val) - float(prev_y)
                ):
                    y_val, strength, width_px = y_retry, s2, w2

        profile[x] = float(y_val)
        prev_y = float(y_val)
        strengths.append(float(strength))
        widths.append(float(width_px))
    return profile, strengths, widths


def _fill_same_surface_holes(profile: np.ndarray, max_hole: int) -> np.ndarray:
    """양 끝 높이가 같은 짧은 누락만 보간해 실제 간격·단 경계는 보존."""
    out = profile.astype(np.float64).copy()
    n = len(out)
    i = 0
    while i < n:
        if not np.isnan(out[i]):
            i += 1
            continue
        j = i
        while j < n and np.isnan(out[j]):
            j += 1
        hole = j - i
        if (
            0 < hole <= max_hole
            and i > 0
            and j < n
            and not np.isnan(out[i - 1])
            and not np.isnan(out[j])
            and abs(float(out[i - 1]) - float(out[j])) <= 5.0
        ):
            out[i:j] = np.linspace(out[i - 1], out[j], hole + 2)[1:-1]
        i = j
    return out


def _reject_spikes_hampel(
    profile: np.ndarray,
    window: int = 31,
    n_sigma: float = 4.0,
    abs_thr: float = 6.0,
    max_spike_run: int = 30,
) -> np.ndarray:
    """국소 중앙값에서 크게 벗어난 '짧은 구간'(스파이크)을 제거.

    이음새/반사에서 몇 열~수십 열만 튀었다가 되돌아오는 노이즈를 잡는다.
    실제 단차는 수백 열에 걸쳐 지속되므로 이상치 '연속 길이'로 구분해 보존한다.
    """
    out = profile.astype(np.float64).copy()
    n = len(out)
    if n == 0:
        return out
    half = max(5, int(window) // 2)

    dev = np.full(n, np.nan)
    for x in range(n):
        if np.isnan(out[x]):
            continue
        lo = max(0, x - half)
        hi = min(n, x + half + 1)
        seg = out[lo:hi]
        seg = seg[~np.isnan(seg)]
        if seg.size < 8:
            continue
        med = float(np.median(seg))
        mad = float(np.median(np.abs(seg - med)))
        scale = max(abs_thr, n_sigma * 1.4826 * mad)
        dev[x] = abs(float(out[x]) - med) - scale  # >0 이면 이상치

    is_out = dev > 0
    # 이상치 연속 구간을 찾아 짧은 것만 제거(NaN)
    x = 0
    while x < n:
        if not is_out[x]:
            x += 1
            continue
        j = x
        while j < n and is_out[j]:
            j += 1
        if (j - x) <= int(max_spike_run):
            out[x:j] = np.nan
        x = j
    return out


def _clean_profile_without_breaking_steps(
    profile: np.ndarray, preserve_gaps: bool = False
) -> np.ndarray:
    """실제 레이저 형상은 유지한 채, 튀는 점(스파이크)과 픽셀 지터만 제거.

    구간을 상수로 평탄화하지 않는다. 이상치(단일 열 스파이크 + 이음새 스파이크)를
    제거하고, 큰 점프(실제 단차)를 넘지 않는 범위에서만 가벼운 median으로 지터를
    다듬는다.
    """
    out = profile.astype(np.float64).copy()
    n = len(out)
    if n == 0:
        return out

    # 1) 단일 열 스파이크 제거: 양옆 중앙값이 서로 비슷한데 자기만 크게 튀면 제거
    source = out.copy()
    radius = 4
    for x in range(radius, n - radius):
        if np.isnan(source[x]):
            continue
        left = source[x - radius : x]
        right = source[x + 1 : x + radius + 1]
        left = left[~np.isnan(left)]
        right = right[~np.isnan(right)]
        if left.size < 2 or right.size < 2:
            continue
        lm = float(np.median(left))
        rm = float(np.median(right))
        if abs(lm - rm) <= 3.0 and abs(float(source[x]) - 0.5 * (lm + rm)) > 6.0:
            out[x] = np.nan

    # 2) 이음새/반사에서 생기는 짧은 스파이크 구간 제거 (Hampel)
    out = _reject_spikes_hampel(out)

    out = _remove_short_runs(out, min_run=max(6, int(round(n * 0.002))))

    # 2) 실제 단차(큰 점프)로 끊은 구간 안에서만 가벼운 median(k=5)으로 지터 제거.
    #    구간을 상수로 만들지 않으므로 실제 레이저의 완만한 굴곡은 그대로 남는다.
    i = 0
    while i < n:
        while i < n and np.isnan(out[i]):
            i += 1
        if i >= n:
            break
        j = i + 1
        while (
            j < n
            and not np.isnan(out[j])
            and abs(float(out[j]) - float(out[j - 1])) <= 10.0
        ):
            j += 1
        if j - i >= 5:
            out[i:j] = _medfilt1d(out[i:j], 5)
        i = j

    if not preserve_gaps:
        out = _fill_same_surface_holes(out, max_hole=max(12, int(round(n * 0.015))))
    return out


def detect_laser_profile(
    undistorted_bgr: np.ndarray,
    roi_y0: Optional[int] = None,
    roi_y1: Optional[int] = None,
    preserve_gaps: bool = False,
    return_quality: bool = False,
    laser_color: str = "blue",
    **_legacy_options,
) -> Tuple[np.ndarray, np.ndarray]:
    """단일 강건 자동 검출기.

    색상 임계값이나 SNR을 사용자가 조절하지 않는다. laser_color("blue"|"red")에
    맞는 선형 응답을 자동 임계화하고, 수평으로 충분히 긴 연결요소만 프로파일로 변환한다.
    """
    if undistorted_bgr is None or undistorted_bgr.size == 0:
        raise ValueError("레이저 검출 이미지가 없습니다")

    color = (laser_color or "blue").lower()
    response = _robust_laser_response(undistorted_bgr, color)
    h, w = response.shape
    if roi_y0 is not None or roi_y1 is not None:
        y0 = 0 if roi_y0 is None else max(0, min(int(roi_y0), h))
        y1 = h if roi_y1 is None else max(0, min(int(roi_y1), h))
        roi = np.zeros_like(response)
        if y1 > y0:
            roi[y0:y1, :] = response[y0:y1, :]
        response = roi

    raw_mask, threshold = _automatic_response_mask(response)
    # 서브픽셀 추출은 원본 밝기 코어를 사용한다. 굵은 코어의 '중간값'은
    # 임계 교차 중점으로 계산한다. 우세 채널은 레이저 색을 따른다.
    b = undistorted_bgr[:, :, 0].astype(np.float64)
    g = undistorted_bgr[:, :, 1].astype(np.float64)
    r = undistorted_bgr[:, :, 2].astype(np.float64)
    main_ch = r if color == "red" else b
    intensity = np.maximum(main_ch, 0.5 * (b + g + r))
    mask, component_count = _keep_line_like_components(raw_mask, response, intensity=intensity)
    profile, strengths, widths = _extract_subpixel_profile(intensity, mask)
    profile = _clean_profile_without_breaking_steps(
        profile, preserve_gaps=bool(preserve_gaps)
    )
    valid_count = int(np.count_nonzero(~np.isnan(profile)))
    if valid_count < max(24, int(round(w * 0.035))):
        profile[:] = np.nan
        mask[:] = 0
        component_count = 0

    if return_quality:
        valid = int(np.count_nonzero(~np.isnan(profile)))
        quality = {
            "detector": f"robust_{color}_ridge_v2",
            "laser_color": color,
            "coverage": round(valid / max(1, w), 3),
            "valid_after_continuity": valid,
            "line_components": int(component_count),
            "response_threshold": round(float(threshold), 3),
            "mean_strength": round(float(np.mean(strengths)), 3) if strengths else None,
            "mean_width_px": round(float(np.mean(widths)), 3) if widths else None,
            "gap_preserved": bool(preserve_gaps),
        }
        return profile, mask, quality
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


def _robust_y_stats(sx: np.ndarray, sy: np.ndarray, edge_margin_ratio: float, trim_ratio: float) -> Optional[dict]:
    """평탄 구간 중앙부만 사용해 robust 대표 y와 품질 통계를 계산."""
    if sx.size == 0 or sy.size == 0:
        return None

    x0 = float(sx[0])
    x1 = float(sx[-1])
    width = max(0.0, x1 - x0)
    margin = width * max(0.0, min(0.45, float(edge_margin_ratio)))
    keep = (sx >= x0 + margin) & (sx <= x1 - margin)
    if int(np.count_nonzero(keep)) < max(5, int(sx.size * 0.35)):
        keep = np.ones_like(sx, dtype=bool)

    used_x = sx[keep]
    used_y = sy[keep].astype(np.float64)
    if used_y.size == 0:
        return None

    sorted_y = np.sort(used_y)
    trim_n = int(round(sorted_y.size * max(0.0, min(0.35, float(trim_ratio)))))
    if trim_n > 0 and sorted_y.size > trim_n * 2 + 2:
        core_y = sorted_y[trim_n:-trim_n]
    else:
        core_y = sorted_y

    extent_px = max(1.0, width + 1.0)
    coverage = float(sx.size) / extent_px
    return {
        "mean_x": round(float(np.median(used_x)), 1),
        "y_pixel": round(float(np.mean(core_y)), 3),
        "median_y": round(float(np.median(used_y)), 3),
        "std_px": round(float(np.std(core_y)), 4),
        "coverage": round(min(1.0, coverage), 3),
        "count": int(core_y.size),
        "source_count": int(sx.size),
        "x0": int(round(x0)),
        "x1": int(round(x1)),
        "used_x0": int(round(float(used_x[0]))),
        "used_x1": int(round(float(used_x[-1]))),
    }


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
    smooth: int = 9,
    edge_k: float = 4.0,
    edge_min: float = 2.0,
    width_ratio: float = 0.28,
    gap_ratio: float = 0.018,
    edge_margin_ratio: float = 0.12,
    trim_ratio: float = 0.12,
    sensitivity: Optional[int] = None,
    y_merge_thr: float = 2.5,
    max_plateau_std: float = 3.5,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """계단 수를 모른 채, 프로파일에서 '평탄 구간(단)'을 자동으로 찾는다.

    y가 평평한 구간 = 한 단, y가 크게 튀는 곳 = 단 경계.
    인접 단 y가 비슷하면 병합하고, std가 큰 경사면(riser)은 제거한다.
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
    ys_s = _medfilt1d(ys, max(5, int(smooth) | 1))

    d = np.abs(np.diff(ys_s))
    thr = _edge_threshold(d, edge_k, edge_min)

    total_extent = float(xs[-1] - xs[0]) if xs.size > 1 else 0.0
    gap_thr = max(6.0, float(gap_ratio) * total_extent)

    bounds = [0]
    for i in range(d.size):
        if d[i] > thr or (xs[i + 1] - xs[i]) > gap_thr:
            bounds.append(i + 1)
    bounds.append(len(xs))

    raw = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        sx = xs[a:b]
        sy = ys[a:b]
        if sx.size == 0:
            continue
        raw.append((sx, sy, float(sx[-1] - sx[0])))
    if not raw:
        return None, "평탄 구간(단)을 찾지 못했습니다"

    if min_width and int(min_width) > 0:
        min_w = float(min_width)
    else:
        widths = np.array([w for (_, _, w) in raw], dtype=np.float64)
        # 노이즈 경계가 raw 폭의 중앙값을 작게 만드는 문제를 막는다.
        min_w = max(
            16.0,
            total_extent * 0.012,
            float(width_ratio) * float(np.percentile(widths, 65)),
        )

    segs = []
    for sx, sy, width in raw:
        if width < min_w or sx.size < max(5, int(min_w) // 2):
            continue
        # 경사면(riser): 직선 기울기가 크면 단이 아님
        if sx.size >= 4:
            slope = float(np.polyfit(sx, sy, 1)[0])
            if abs(slope) > 0.35:
                continue
        stats = _robust_y_stats(sx, sy, edge_margin_ratio, trim_ratio)
        if stats is None:
            continue
        if float(stats.get("std_px") or 0) > float(max_plateau_std):
            continue
        if float(stats.get("coverage") or 0) < 0.40:
            continue
        segs.append(stats)

    if not segs:
        return None, "평탄 구간(단)을 찾지 못했습니다 (검출 확인)"

    # 인접 단 y가 거의 같으면 병합 (과다 분할 억제)
    merged: List[dict] = [dict(segs[0])]
    for s in segs[1:]:
        prev = merged[-1]
        if abs(float(s["y_pixel"]) - float(prev["y_pixel"])) <= float(y_merge_thr):
            # 가중 평균으로 합침
            c0 = max(1, int(prev.get("count") or 1))
            c1 = max(1, int(s.get("count") or 1))
            prev["y_pixel"] = round((prev["y_pixel"] * c0 + s["y_pixel"] * c1) / (c0 + c1), 3)
            prev["mean_x"] = round((prev["mean_x"] * c0 + s["mean_x"] * c1) / (c0 + c1), 1)
            prev["count"] = c0 + c1
            prev["x0"] = min(int(prev.get("x0") or prev["mean_x"]), int(s.get("x0") or s["mean_x"]))
            prev["x1"] = max(int(prev.get("x1") or prev["mean_x"]), int(s.get("x1") or s["mean_x"]))
            prev["std_px"] = round(
                max(float(prev.get("std_px") or 0), float(s.get("std_px") or 0)), 4
            )
        else:
            merged.append(dict(s))

    # 양옆 높이가 같은 짧은 섬은 반사/노이즈가 만든 가짜 단으로 본다.
    if len(merged) >= 3:
        cleaned: List[dict] = []
        i = 0
        while i < len(merged):
            if 0 < i < len(merged) - 1:
                prev = merged[i - 1]
                cur = merged[i]
                nxt = merged[i + 1]
                outer_delta = abs(float(prev["y_pixel"]) - float(nxt["y_pixel"]))
                cur_delta = min(
                    abs(float(cur["y_pixel"]) - float(prev["y_pixel"])),
                    abs(float(cur["y_pixel"]) - float(nxt["y_pixel"])),
                )
                cur_width = float(cur.get("x1", 0)) - float(cur.get("x0", 0))
                if (
                    outer_delta <= float(y_merge_thr)
                    and cur_delta > float(y_merge_thr)
                    and cur_width < max(24.0, total_extent * 0.045)
                ):
                    i += 1
                    continue
            cleaned.append(merged[i])
            i += 1
        merged = cleaned

    return merged, None


def build_lut_auto(
    points: list,
    increment_mm: float,
    base_mm: float = 0.0,
    reverse_order: bool = False,
    min_width: int = 0,
    sensitivity: int = 40,
    edge_margin_ratio: float = 0.12,
    trim_ratio: float = 0.12,
) -> Tuple[Optional[List[dict]], Optional[str]]:
    """여러 경계 강도에서 반복 검출해 가장 안정적으로 반복되는 단 구성을 선택."""
    # UI 민감도와 무관한 고정 후보군. 실제 단은 여러 강도에서 같은 개수로 반복된다.
    ordered = [10, 20, 30, 40, 50, 60, 70]
    results = []
    best_err = None
    for sens in ordered:
        segs, err = auto_segment_steps(
            points,
            min_width=min_width,
            sensitivity=sens,
            edge_margin_ratio=edge_margin_ratio,
            trim_ratio=trim_ratio,
            # 노이즈로 인한 가짜 단 병합: LUT는 더 관대하게 합침
            y_merge_thr=4.0,
            max_plateau_std=4.0,
        )
        if err or not segs:
            best_err = err
            continue
        n = len(segs)
        if 2 <= n <= 12:
            std_mean = float(np.mean([float(s.get("std_px") or 0) for s in segs]))
            coverage = float(np.mean([float(s.get("coverage") or 0) for s in segs]))
            results.append((n, std_mean, coverage, sens, segs))

    if not results:
        return None, best_err or "단을 2개 이상 찾지 못했습니다 (레이저 선·계단 전체가 화면에 들어오는지 확인)"

    frequency = {}
    for n, *_rest in results:
        frequency[n] = frequency.get(n, 0) + 1
    # 반복 횟수 우선, 동일하면 평탄도·커버리지가 좋은 결과를 선택한다.
    _n, _std, _coverage, _sens, segs = min(
        results,
        key=lambda item: (
            -frequency[item[0]],
            item[1],
            -item[2],
        ),
    )
    if len(segs) < 2:
        return None, "단을 2개 이상 찾지 못했습니다 (레이저 선·계단 전체가 화면에 들어오는지 확인)"

    segs = list(segs)
    segs.sort(key=lambda s: s["mean_x"], reverse=reverse_order)
    table = []
    for i, s in enumerate(segs):
        table.append(
            {
                "y_pixel": s["y_pixel"],
                "height_mm": round(base_mm + i * increment_mm, 4),
                "mean_x": s["mean_x"],
                "count": s["count"],
                "std_px": s.get("std_px"),
                "coverage": s.get("coverage"),
                "x0": s.get("x0"),
                "x1": s.get("x1"),
                "used_x0": s.get("used_x0"),
                "used_x1": s.get("used_x1"),
                "source_count": s.get("source_count"),
            }
        )
    return table, None


def merge_profiles_median(profiles: List[np.ndarray]) -> Optional[np.ndarray]:
    """여러 프레임의 x→y profile을 열별 median으로 병합."""
    usable = [p for p in profiles if p is not None and len(p) > 0]
    if not usable:
        return None
    width = max(len(p) for p in usable)
    stack = np.full((len(usable), width), np.nan, dtype=np.float64)
    for i, p in enumerate(usable):
        stack[i, : len(p)] = p
    valid = np.any(~np.isnan(stack), axis=0)
    merged = np.full(width, np.nan, dtype=np.float64)
    if np.any(valid):
        merged[valid] = np.nanmedian(stack[:, valid], axis=0)
    return merged


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


def _lut_legacy_path(calib_dir: str, camera_id: int) -> str:
    return os.path.join(calib_dir, f"camera_{camera_id}_lut.json")


def _sanitize_lut_slug(name: str) -> str:
    """파일명용 slug (빈 문자열이면 자동 이름 사용)."""
    text = (name or "").strip()
    if not text:
        return ""
    slug = re.sub(r"[^\w\-가-힣]+", "_", text, flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:48]


def _lut_filename(camera_id: int, created_at: str, lut_name: Optional[str] = None) -> str:
    slug = _sanitize_lut_slug(lut_name)
    if slug:
        return f"camera_{camera_id}_lut_{slug}_{created_at}.json"
    return f"camera_{camera_id}_lut_{created_at}.json"


def lut_name_from_filename(filename: str) -> Optional[str]:
    """파일명 slug에서 표시용 LUT 이름 추출 (JSON에 없을 때 fallback)."""
    base = os.path.basename(filename or "")
    if re.fullmatch(r"camera_\d+_lut\.json", base):
        return None
    m = re.match(r"^camera_\d+_lut_(.+)\.json$", base)
    if not m:
        return None
    middle = m.group(1)
    if re.fullmatch(r"\d{8}_\d{6}", middle):
        return None
    tm = re.match(r"^(.+)_(\d{8}_\d{6})$", middle)
    if not tm:
        return None
    slug = tm.group(1).strip()
    return slug or None


def lut_display_name(meta: dict, filename: Optional[str] = None) -> Optional[str]:
    stored = (meta.get("lut_name") or "").strip()
    if stored:
        return stored
    fname = filename or meta.get("_lut_file") or ""
    return lut_name_from_filename(fname)


def list_lut_files(calib_dir: str, camera_id: Optional[int] = None) -> List[str]:
    """LUT json 경로 목록 (최신순). camera_id 지정 시 해당 카메라만."""
    pattern = os.path.join(calib_dir, "camera_*_lut*.json")
    files = glob.glob(pattern)
    if camera_id is not None:
        prefix = f"camera_{camera_id}_lut"
        files = [f for f in files if os.path.basename(f).startswith(prefix)]
    return sorted(files, reverse=True)


def resolve_lut_path(calib_dir: str, camera_id: int, lut_file: Optional[str] = None) -> Optional[str]:
    """lut_file 지정 시 해당 파일, 없으면 카메라별 최신 LUT (구형 단일 파일 fallback)."""
    if lut_file:
        path = os.path.join(calib_dir, os.path.basename(lut_file))
        return path if os.path.exists(path) else None
    files = list_lut_files(calib_dir, camera_id)
    if files:
        return files[0]
    legacy = _lut_legacy_path(calib_dir, camera_id)
    return legacy if os.path.exists(legacy) else None


def save_lut(calib_dir: str, camera_id: int, table: List[dict], meta: dict) -> str:
    os.makedirs(calib_dir, exist_ok=True)
    created_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    lut_name = (meta.get("lut_name") or "").strip() or None
    filename = _lut_filename(camera_id, created_at, lut_name)
    path = os.path.join(calib_dir, filename)
    payload = {
        "camera_id": camera_id,
        "created_at": created_at,
        "step_count": len(table),
        "table": table,
        **{k: v for k, v in meta.items() if k != "lut_name"},
    }
    if lut_name:
        payload["lut_name"] = lut_name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def load_lut(calib_dir: str, camera_id: int, lut_file: Optional[str] = None) -> Optional[dict]:
    path = resolve_lut_path(calib_dir, camera_id, lut_file)
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_lut_file"] = os.path.basename(path)
    if not (data.get("lut_name") or "").strip():
        derived = lut_name_from_filename(data["_lut_file"])
        if derived:
            data["lut_name"] = derived
    return data


def delete_lut(calib_dir: str, camera_id: int, lut_file: str) -> Tuple[bool, Optional[str], dict]:
    """LUT json과 연결된 이미지 파일을 삭제.

    반환: (ok, error, info)
    """
    fname = os.path.basename(lut_file or "")
    if not fname or not fname.endswith(".json"):
        return False, "유효한 LUT 파일명이 아닙니다.", {}
    if not fname.startswith(f"camera_{int(camera_id)}_lut"):
        return False, "해당 카메라의 LUT가 아닙니다.", {}

    path = os.path.join(calib_dir, fname)
    if not os.path.exists(path):
        return False, "LUT 파일을 찾을 수 없습니다.", {}

    image_file = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        image_file = os.path.basename(meta.get("image_file") or "") or None
    except Exception:
        meta = {}

    # json과 같은 basename의 jpg도 후보
    sibling_jpg = f"{os.path.splitext(fname)[0]}.jpg"
    deleted = {"lut_file": fname, "image_files": []}

    try:
        os.remove(path)
    except Exception as e:
        return False, f"LUT 삭제 실패: {e}", deleted

    for img_name in {image_file, sibling_jpg}:
        if not img_name:
            continue
        img_path = os.path.join(calib_dir, os.path.basename(img_name))
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
                deleted["image_files"].append(os.path.basename(img_path))
            except Exception:
                pass

    return True, None, deleted


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


def roi_median_y(profile: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> Optional[float]:
    """사각형 ROI 안을 지나는 레이저 profile 점들의 대표 y."""
    x0, x1 = sorted((int(x0), int(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    x0 = max(0, x0)
    x1 = min(len(profile) - 1, x1)
    if x1 <= x0:
        return None
    xs = np.arange(x0, x1 + 1)
    ys = profile[x0 : x1 + 1]
    valid = (~np.isnan(ys)) & (ys >= y0) & (ys <= y1)
    if not np.any(valid):
        return None
    return float(np.median(ys[valid]))


# ─────────────────────────────────────────────────────────────
# 간격(Gap): 레이저 직선 끝점 검출 → 두 부위 사이 거리
# ─────────────────────────────────────────────────────────────

DEFAULT_GAP_MIN_SEGMENT_PX = 12
DEFAULT_GAP_MAX_NAN_BRIDGE = 2
DEFAULT_GAP_FIT_LEN = 16
DEFAULT_GAP_MIN_PX = 2.0
DEFAULT_GAP_MAX_PX = 400.0


def _keep_top_lines(mask: np.ndarray, bridge_gap: int = 1, top_n: int = 2) -> np.ndarray:
    """가로로 넓은 상위 N개 연결요소만 남긴다 (단차+간격 동시·간격 양옆 레이저용)."""
    if mask is None or not np.any(mask):
        return mask
    work = mask.copy()
    bg = max(1, int(bridge_gap or 1))
    if bg > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (bg, 1))
        work = cv2.morphologyEx(work, cv2.MORPH_CLOSE, kernel)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(work, 8)
    if num <= 2:
        return mask

    scored = []
    for i in range(1, num):
        score = stats[i, cv2.CC_STAT_WIDTH] * 100000 + stats[i, cv2.CC_STAT_AREA]
        scored.append((score, i))
    scored.sort(reverse=True)
    keep_ids = {i for _, i in scored[: max(1, int(top_n))]}
    keep = np.zeros_like(mask)
    for i in keep_ids:
        keep[labels == i] = mask[labels == i]
    return keep


def detect_laser_profile_for_gap(
    undistorted_bgr: np.ndarray,
    **kwargs,
) -> Tuple[np.ndarray, np.ndarray]:
    """간격 측정용: 실제 빈 구간을 보간하지 않는 동일 자동 검출기."""
    kwargs = dict(kwargs)
    kwargs["preserve_gaps"] = True
    return detect_laser_profile(undistorted_bgr, **kwargs)

def find_laser_segments(
    profile: np.ndarray,
    min_segment_px: int = DEFAULT_GAP_MIN_SEGMENT_PX,
    max_nan_bridge: int = DEFAULT_GAP_MAX_NAN_BRIDGE,
    jump_thr: Optional[float] = None,
) -> List[dict]:
    """프로파일을 연속 직선 구간으로 분할.

    - NaN 구멍(짧은 누락)은 max_nan_bridge 이하면 이어 붙임
    - |Δy|가 jump_thr 이상이면 끊김/이상 현상으로 분할
    """
    if profile is None or len(profile) == 0:
        return []
    w = len(profile)
    valid = ~np.isnan(profile)

    # 짧은 NaN 브릿지
    bridged = valid.copy()
    mb = max(0, int(max_nan_bridge))
    if mb > 0:
        i = 0
        while i < w:
            if bridged[i]:
                i += 1
                continue
            j = i
            while j < w and not bridged[j]:
                j += 1
            hole = j - i
            if 0 < hole <= mb and i > 0 and j < w and valid[i - 1] and valid[j]:
                bridged[i:j] = True
            i = j

    if jump_thr is None:
        # 유효 점의 이웃 |Δy| 분포로 자동 임계
        ys = profile[valid]
        if ys.size >= 4:
            d = np.abs(np.diff(ys))
            med = float(np.median(d))
            mad = float(np.median(np.abs(d - med)))
            jump_thr = max(3.0, med + 6.0 * max(mad * 1.4826, 0.3))
        else:
            jump_thr = 8.0

    segments: List[dict] = []
    start = None
    prev_x = None
    prev_y = None

    def _flush(end_x: int):
        nonlocal start
        if start is None:
            return
        xs = np.arange(start, end_x + 1)
        ys = profile[start : end_x + 1].astype(np.float64)
        ok = ~np.isnan(ys)
        if int(np.count_nonzero(ok)) < max(3, int(min_segment_px) // 3):
            start = None
            return
        xs_v = xs[ok].astype(np.float64)
        ys_v = ys[ok]
        length = float(xs_v[-1] - xs_v[0]) if xs_v.size else 0.0
        if length < float(min_segment_px) and xs_v.size < max(5, int(min_segment_px) // 2):
            start = None
            return
        segments.append(
            {
                "x0": int(xs_v[0]),
                "x1": int(xs_v[-1]),
                "length_px": round(length, 2),
                "count": int(xs_v.size),
                "mean_y": round(float(np.median(ys_v)), 3),
                "xs": xs_v,
                "ys": ys_v,
            }
        )
        start = None

    for x in range(w):
        if not bridged[x]:
            if start is not None and prev_x is not None:
                _flush(prev_x)
            prev_x, prev_y = None, None
            continue
        # 짧은 NaN 구멍은 세그먼트를 유지(끝점 계산은 유효 점만 사용)
        if np.isnan(profile[x]):
            continue
        y = float(profile[x])
        if start is None:
            start = x
            prev_x, prev_y = x, y
            continue
        # 큰 y 점프 → 직선 끝 / 이상 끊김
        if prev_y is not None and abs(y - prev_y) > float(jump_thr):
            _flush(prev_x)
            start = x
        prev_x, prev_y = x, y

    if start is not None and prev_x is not None:
        _flush(prev_x)
    return segments


def refine_line_end(
    xs: np.ndarray,
    ys: np.ndarray,
    side: str = "right",
    fit_len: int = DEFAULT_GAP_FIT_LEN,
) -> Optional[dict]:
    """직선 끝점: 끝쪽 fit_len 점으로 1차 피팅 후 끝 좌표를 서브픽셀로 확정."""
    if xs is None or ys is None or len(xs) < 3:
        return None
    n = min(max(3, int(fit_len)), len(xs))
    if side == "left":
        fx, fy = xs[:n], ys[:n]
        end_x = float(xs[0])
    else:
        fx, fy = xs[-n:], ys[-n:]
        end_x = float(xs[-1])

    # y = a + b x
    A = np.vstack([np.ones_like(fx), fx]).T
    try:
        coef, *_ = np.linalg.lstsq(A, fy, rcond=None)
    except Exception:
        return {
            "x": round(end_x, 3),
            "y": round(float(fy[-1] if side == "right" else fy[0]), 3),
            "slope": 0.0,
            "rmse": None,
        }
    a, b = float(coef[0]), float(coef[1])
    pred = a + b * fx
    rmse = float(np.sqrt(np.mean((fy - pred) ** 2)))
    end_y = float(a + b * end_x)
    return {
        "x": round(end_x, 3),
        "y": round(end_y, 3),
        "slope": round(b, 5),
        "rmse": round(rmse, 4),
        "fit_count": int(n),
    }


def _facing_dy(left: dict, right: dict, n: int = 8) -> float:
    """left 세그먼트 끝쪽 / right 세그먼트 시작쪽 y 중앙값 차이 (단차 크기)."""
    ly = float(np.median(left["ys"][-n:]))
    ry = float(np.median(right["ys"][:n]))
    return abs(ry - ly)


def _column_peak(intensity: np.ndarray, profile: np.ndarray, x: int, half: int = 25) -> float:
    """컬럼 x에서 프로파일 y 주변의 피크 밝기."""
    y = profile[int(x)]
    if np.isnan(y):
        return 0.0
    y = int(round(y))
    y0 = max(0, y - half)
    y1 = min(intensity.shape[0], y + half + 1)
    return float(intensity[y0:y1, int(x)].max())


def _bright_endpoint(
    intensity: np.ndarray,
    profile: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    side: str,
    ratio: float = 0.8,
    floor: float = 300.0,
    n: int = 9,
) -> Optional[dict]:
    """밝은 코어 기준 끝점: 세그먼트 중앙부 피크의 ratio 이상인 마지막 컬럼.

    레이저 끝에서 코너를 감싸는 어두운 글로우 꼬리를 제외해, 양쪽 끝점을
    '가장 밝은 코어가 끝나는 곳'이라는 동일 기준으로 확정한다.
    """
    if xs is None or len(xs) < 8:
        return None
    xi = xs.astype(int)
    # 기준 밝기: 세그먼트 중앙 50% 컬럼들의 피크 중앙값 (샘플링으로 상한 200개)
    mid = xi[len(xi) // 4: max(len(xi) // 4 + 1, 3 * len(xi) // 4)]
    step = max(1, len(mid) // 200)
    ref = float(np.median([_column_peak(intensity, profile, x) for x in mid[::step]]))
    thr = max(floor, ratio * ref)

    order = xi[::-1] if side == "right" else xi  # 끝에서 안쪽으로
    ex = None
    for x in order:
        if _column_peak(intensity, profile, x) >= thr:
            ex = int(x)
            break
    if ex is None:
        return None
    sel = int(np.flatnonzero(xi == ex)[0])
    if side == "right":
        ys_n = ys[max(0, sel - n + 1): sel + 1]
    else:
        ys_n = ys[sel: sel + n]
    return {
        "x": round(float(ex), 3),
        "y": round(float(np.median(ys_n)), 3),
        "ref_peak": round(ref, 1),
        "threshold": round(thr, 1),
    }


def measure_gap_from_profile(
    profile: np.ndarray,
    min_segment_px: int = DEFAULT_GAP_MIN_SEGMENT_PX,
    max_nan_bridge: int = DEFAULT_GAP_MAX_NAN_BRIDGE,
    fit_len: int = DEFAULT_GAP_FIT_LEN,
    min_gap_px: float = DEFAULT_GAP_MIN_PX,
    max_gap_px: float = DEFAULT_GAP_MAX_PX,
    mm_per_px: Optional[float] = None,
    search_x0: Optional[int] = None,
    search_x1: Optional[int] = None,
    min_step_dy_px: Optional[float] = None,
    intensity: Optional[np.ndarray] = None,
    bright_ratio: float = 0.8,
    bright_floor: float = 300.0,
) -> Tuple[Optional[dict], Optional[str]]:
    """레이저 직선 끝점 사이 간격을 측정.

    1) 프로파일을 직선 세그먼트로 분할
    2) 인접 세그먼트 쌍 중 간격 후보 점수화 (폭·길이·중앙 근접·단차 Δy)
    3) 양쪽 끝점을 직선 피팅으로 확정 후 Δx / 유클리드 거리 반환

    min_step_dy_px가 주어지면 마주보는 끝쪽 y 차이가 그 이상인
    '다른 단' 세그먼트 쌍만 후보로 삼는다.
    intensity(원본 밝기 맵)가 주어지면 '밝은 코어 기준 끝점'도 함께 확정해
    gap_bright_px/mm를 계산한다 — 글로우 꼬리를 제외한 값으로, 권장 측정값.
    """
    if profile is None or len(profile) < 10:
        return None, "레이저 프로파일이 없습니다"

    segs = find_laser_segments(
        profile,
        min_segment_px=min_segment_px,
        max_nan_bridge=max_nan_bridge,
    )
    if len(segs) < 2:
        return None, (
            "레이저가 끊긴 두 구간을 찾지 못했습니다. "
            "간격 양쪽의 레이저 선이 화면에 충분히 들어오는지 확인하세요."
        )

    w = len(profile)
    cx = 0.5 * (w - 1)
    x0s = 0 if search_x0 is None else max(0, int(search_x0))
    x1s = w - 1 if search_x1 is None else min(w - 1, int(search_x1))

    # 이 이상 y가 벌어진 마주보는 쌍은 '다른 단'으로 간주 (min_gap_px 하한 면제)
    step_dy_ref = 3.0

    candidates = []
    n_seg = len(segs)
    for i in range(n_seg - 1):
        left = segs[i]
        # 사이의 '간격 바닥' 조각(양쪽 면보다 깊고 짧은 세그먼트)은 건너뛰어
        # 두 물체 면끼리 짝지을 수 있게 한다 (최대 2개까지 건너뜀).
        for j in range(i + 1, min(i + 4, n_seg)):
            right = segs[j]
            mids = segs[i + 1: j]
            if mids:
                ly = float(np.median(left["ys"][-8:]))
                ry = float(np.median(right["ys"][:8]))
                floor_y = max(ly, ry) + 20.0  # 이미지 y는 아래로 증가 → 더 깊은 곳
                min_len = min(left["length_px"], right["length_px"])
                if not all(
                    m["mean_y"] > floor_y and m["length_px"] < 0.5 * min_len
                    for m in mids
                ):
                    continue
            gap_x0 = float(left["x1"])
            gap_x1 = float(right["x0"])
            gap_w = gap_x1 - gap_x0
            step_dy = _facing_dy(left, right)
            if min_step_dy_px is not None and step_dy < float(min_step_dy_px):
                continue
            # 다른 단 쌍은 x 간격이 거의 없어도(순수 y 점프) 후보로 허용
            gap_floor = 0.0 if step_dy >= step_dy_ref else float(min_gap_px)
            if gap_w < gap_floor or gap_w > float(max_gap_px):
                continue
            mid = 0.5 * (gap_x0 + gap_x1)
            if mid < x0s or mid > x1s:
                continue
            # 점수: 양쪽이 길고, 간격이 너무 크지 않으며, 화면 중앙에 가까울수록 가산
            len_score = min(left["length_px"], right["length_px"])
            center_pen = abs(mid - cx) / max(cx, 1.0)
            # 차량 갭 ~수~수십 px 가정: 중간 폭 선호
            width_score = 1.0 / (1.0 + abs(gap_w - 20.0) / 30.0)
            # 단차 보너스: 다른 단(끝쪽 y 차이가 큰) 쌍을 같은 높이 끊김보다 우선 (최대 2배)
            step_bonus = 1.0 + min(step_dy, 30.0) / 30.0
            score = len_score * width_score * (1.0 - 0.35 * center_pen) * step_bonus
            candidates.append((score, i, left, right, gap_w))

    if not candidates:
        return None, "유효한 간격 후보가 없습니다 (min/max gap 또는 검색 구간 확인)"

    candidates.sort(key=lambda t: t[0], reverse=True)
    _score, _i, left, right, _gw = candidates[0]

    left_end = refine_line_end(left["xs"], left["ys"], side="right", fit_len=fit_len)
    right_end = refine_line_end(right["xs"], right["ys"], side="left", fit_len=fit_len)
    if left_end is None or right_end is None:
        return None, "직선 끝점 피팅에 실패했습니다"

    dx = float(right_end["x"] - left_end["x"])
    dy = float(right_end["y"] - left_end["y"])
    gap_px = abs(dx)
    gap_euclid_px = float(np.hypot(dx, dy))

    # 밝은 코어 기준 끝점 (글로우 꼬리 제외) — intensity가 있을 때만
    left_bright = right_bright = None
    gap_bright_px = None
    if intensity is not None:
        left_bright = _bright_endpoint(
            intensity, profile, left["xs"], left["ys"], "right", bright_ratio, bright_floor
        )
        right_bright = _bright_endpoint(
            intensity, profile, right["xs"], right["ys"], "left", bright_ratio, bright_floor
        )
        if left_bright and right_bright:
            gap_bright_px = abs(float(right_bright["x"] - left_bright["x"]))

    gap_mm = None
    gap_euclid_mm = None
    gap_bright_mm = None
    scale = None if mm_per_px is None else float(mm_per_px)
    if scale is not None and scale > 0:
        gap_mm = round(gap_px * scale, 4)
        gap_euclid_mm = round(gap_euclid_px * scale, 4)
        if gap_bright_px is not None:
            gap_bright_mm = round(gap_bright_px * scale, 4)

    # 응답용 세그먼트 요약 (대용량 xs/ys 제외)
    def _summ(s: dict) -> dict:
        return {
            "x0": s["x0"],
            "x1": s["x1"],
            "length_px": s["length_px"],
            "count": s["count"],
            "mean_y": s["mean_y"],
        }

    result = {
        "gap_px": round(gap_px, 3),
        "gap_euclid_px": round(gap_euclid_px, 3),
        "gap_mm": gap_mm,
        "gap_euclid_mm": gap_euclid_mm,
        "gap_bright_px": None if gap_bright_px is None else round(gap_bright_px, 3),
        "gap_bright_mm": gap_bright_mm,
        "mm_per_px": scale,
        "step_dy_px": round(abs(dy), 3),
        "left_end": left_end,
        "right_end": right_end,
        "left_end_bright": left_bright,
        "right_end_bright": right_bright,
        "left_segment": _summ(left),
        "right_segment": _summ(right),
        "segment_count": len(segs),
        "segments": [_summ(s) for s in segs],
        "candidate_count": len(candidates),
        "mode": "auto",
    }
    return result, None


def _points_in_roi(
    profile: np.ndarray, x0: int, y0: int, x1: int, y1: int
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """ROI 안을 지나는 레이저 점 (xs, ys)."""
    x0, x1 = sorted((int(x0), int(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    x0 = max(0, x0)
    x1 = min(len(profile) - 1, x1)
    if x1 <= x0:
        return None, None
    xs = np.arange(x0, x1 + 1)
    ys = profile[x0 : x1 + 1].astype(np.float64)
    ok = (~np.isnan(ys)) & (ys >= y0) & (ys <= y1)
    if not np.any(ok):
        return None, None
    return xs[ok].astype(np.float64), ys[ok]


def measure_gap_from_rois(
    profile: np.ndarray,
    a_roi: dict,
    b_roi: dict,
    fit_len: int = DEFAULT_GAP_FIT_LEN,
    mm_per_px: Optional[float] = None,
    intensity: Optional[np.ndarray] = None,
    bright_ratio: float = 0.8,
    bright_floor: float = 300.0,
) -> Tuple[Optional[dict], Optional[str]]:
    """A/B ROI 안 레이저의 마주보는 끝점 사이 간격.

    mean_x가 작은 쪽을 Left, 큰 쪽을 Right로 두고
    Left의 오른쪽 끝 ↔ Right의 왼쪽 끝 거리를 잰다.
    """
    if profile is None or len(profile) < 10:
        return None, "레이저 프로파일이 없습니다"
    if not a_roi or not b_roi:
        return None, "A/B ROI를 모두 지정하세요"

    ax0, ay0, ax1, ay1 = a_roi["x0"], a_roi["y0"], a_roi["x1"], a_roi["y1"]
    bx0, by0, bx1, by1 = b_roi["x0"], b_roi["y0"], b_roi["x1"], b_roi["y1"]

    axs, ays = _points_in_roi(profile, ax0, ay0, ax1, ay1)
    bxs, bys = _points_in_roi(profile, bx0, by0, bx1, by1)
    if axs is None or len(axs) < 3:
        return None, "A ROI에서 레이저 점이 부족합니다"
    if bxs is None or len(bxs) < 3:
        return None, "B ROI에서 레이저 점이 부족합니다"

    a_mean_x = float(np.median(axs))
    b_mean_x = float(np.median(bxs))
    if a_mean_x <= b_mean_x:
        left_xs, left_ys, right_xs, right_ys = axs, ays, bxs, bys
        left_label, right_label = "A", "B"
        left_roi, right_roi = a_roi, b_roi
    else:
        left_xs, left_ys, right_xs, right_ys = bxs, bys, axs, ays
        left_label, right_label = "B", "A"
        left_roi, right_roi = b_roi, a_roi

    left_end = refine_line_end(left_xs, left_ys, side="right", fit_len=fit_len)
    right_end = refine_line_end(right_xs, right_ys, side="left", fit_len=fit_len)
    if left_end is None or right_end is None:
        return None, "A/B 직선 끝점 피팅에 실패했습니다"

    dx = float(right_end["x"] - left_end["x"])
    dy = float(right_end["y"] - left_end["y"])
    gap_px = abs(dx)
    gap_euclid_px = float(np.hypot(dx, dy))

    # 밝은 코어 기준 끝점 (글로우 꼬리 제외)
    left_bright = right_bright = None
    gap_bright_px = None
    if intensity is not None:
        left_bright = _bright_endpoint(
            intensity, profile, left_xs, left_ys, "right", bright_ratio, bright_floor
        )
        right_bright = _bright_endpoint(
            intensity, profile, right_xs, right_ys, "left", bright_ratio, bright_floor
        )
        if left_bright and right_bright:
            gap_bright_px = abs(float(right_bright["x"] - left_bright["x"]))

    gap_mm = None
    gap_euclid_mm = None
    gap_bright_mm = None
    scale = None if mm_per_px is None else float(mm_per_px)
    if scale is not None and scale > 0:
        gap_mm = round(gap_px * scale, 4)
        gap_euclid_mm = round(gap_euclid_px * scale, 4)
        if gap_bright_px is not None:
            gap_bright_mm = round(gap_bright_px * scale, 4)

    def _seg(xs, ys, roi, label):
        return {
            "label": label,
            "x0": int(xs[0]),
            "x1": int(xs[-1]),
            "length_px": round(float(xs[-1] - xs[0]), 2),
            "count": int(len(xs)),
            "mean_y": round(float(np.median(ys)), 3),
            "roi": {
                "x0": int(roi["x0"]),
                "y0": int(roi["y0"]),
                "x1": int(roi["x1"]),
                "y1": int(roi["y1"]),
            },
        }

    result = {
        "gap_px": round(gap_px, 3),
        "gap_euclid_px": round(gap_euclid_px, 3),
        "gap_mm": gap_mm,
        "gap_euclid_mm": gap_euclid_mm,
        "gap_bright_px": None if gap_bright_px is None else round(gap_bright_px, 3),
        "gap_bright_mm": gap_bright_mm,
        "mm_per_px": scale,
        "left_end": left_end,
        "right_end": right_end,
        "left_end_bright": left_bright,
        "right_end_bright": right_bright,
        "left_segment": _seg(left_xs, left_ys, left_roi, left_label),
        "right_segment": _seg(right_xs, right_ys, right_roi, right_label),
        "segment_count": 2,
        "segments": [
            _seg(left_xs, left_ys, left_roi, left_label),
            _seg(right_xs, right_ys, right_roi, right_label),
        ],
        "candidate_count": 1,
        "mode": "roi",
        "a_roi": {"x0": int(ax0), "y0": int(ay0), "x1": int(ax1), "y1": int(ay1)},
        "b_roi": {"x0": int(bx0), "y0": int(by0), "x1": int(bx1), "y1": int(by1)},
    }
    return result, None


def gap_scale_path(calib_dir: str, camera_id: int) -> str:
    return os.path.join(calib_dir, f"camera_{int(camera_id)}_gap_scale.json")


def save_gap_scale(calib_dir: str, camera_id: int, payload: dict) -> str:
    os.makedirs(calib_dir, exist_ok=True)
    path = gap_scale_path(calib_dir, camera_id)
    data = dict(payload or {})
    data["camera_id"] = int(camera_id)
    data["saved_at"] = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_gap_scale(calib_dir: str, camera_id: int) -> Optional[dict]:
    path = gap_scale_path(calib_dir, camera_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def attach_plane_scale_to_calibration(
    calib_dir: str, calibration_file: str, plane_scale: dict
) -> str:
    """캘리브레이션 JSON에 plane_scale(작업거리 mm/px)을 함께 저장."""
    fname = os.path.basename(calibration_file or "")
    if not fname:
        raise ValueError("calibration_file이 필요합니다")
    path = os.path.join(calib_dir, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(f"캘리브레이션 파일 없음: {fname}")
    with open(path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    data = dict(plane_scale or {})
    data["saved_at"] = stamp
    meta["plane_scale"] = data
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return path


def load_plane_scale_from_calibration(
    calib_dir: str, calibration_file: Optional[str]
) -> Optional[dict]:
    if not calibration_file:
        return None
    path = os.path.join(calib_dir, os.path.basename(calibration_file))
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        ps = meta.get("plane_scale")
        return ps if isinstance(ps, dict) else None
    except Exception:
        return None


def estimate_checker_square_px(
    corners: np.ndarray, inner_cols: int, inner_rows: int
) -> dict:
    """내부 코너 격자에서 가로/세로/전체 한 칸 픽셀 길이(median)."""
    cols, rows = int(inner_cols), int(inner_rows)
    grid = corners.reshape(rows, cols, 2).astype(np.float64)
    horiz: List[float] = []
    vert: List[float] = []
    for r in range(rows):
        for c in range(cols - 1):
            horiz.append(float(np.linalg.norm(grid[r, c + 1] - grid[r, c])))
    for c in range(cols):
        for r in range(rows - 1):
            vert.append(float(np.linalg.norm(grid[r + 1, c] - grid[r, c])))
    all_d = horiz + vert
    return {
        "square_px_x": float(np.median(horiz)) if horiz else None,
        "square_px_y": float(np.median(vert)) if vert else None,
        "square_px": float(np.median(all_d)) if all_d else None,
        "n_horiz": len(horiz),
        "n_vert": len(vert),
    }


def compute_mm_per_px_from_checker(
    square_size_mm: float,
    square_px: float,
) -> Optional[float]:
    """mm/px = square_size_mm / square_px."""
    if square_size_mm is None or square_px is None:
        return None
    sq = float(square_px)
    if sq <= 1e-6:
        return None
    return float(square_size_mm) / sq


def draw_gap_overlay(
    img: np.ndarray,
    profile: np.ndarray,
    gap: dict,
    color_line: Tuple[int, int, int] = (0, 255, 255),
    color_gap: Tuple[int, int, int] = (0, 165, 255),
) -> np.ndarray:
    """간격 측정 결과 오버레이: 레이저 점 + 양쪽 끝 + 간격 선 (+ ROI)."""
    out = draw_profile(img, profile, color=color_line)
    if not gap:
        return out

    for key, color in (("a_roi", (0, 255, 0)), ("b_roi", (0, 0, 255))):
        roi = gap.get(key)
        if not roi:
            continue
        x0, x1 = sorted((int(roi["x0"]), int(roi["x1"])))
        y0, y1 = sorted((int(roi["y0"]), int(roi["y1"])))
        cv2.rectangle(out, (x0, y0), (x1, y1), color, 2)
        cv2.putText(
            out, key[0].upper(), (x0, max(14, y0 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA,
        )

    le = gap.get("left_end") or {}
    re = gap.get("right_end") or {}
    try:
        x0, y0 = int(round(le["x"])), int(round(le["y"]))
        x1, y1 = int(round(re["x"])), int(round(re["y"]))
    except Exception:
        return out

    h = out.shape[0]
    cv2.circle(out, (x0, y0), 6, (0, 255, 0), 2)
    cv2.circle(out, (x1, y1), 6, (0, 0, 255), 2)
    cv2.line(out, (x0, max(0, y0 - 40)), (x0, min(h - 1, y0 + 40)), (0, 255, 0), 1)
    cv2.line(out, (x1, max(0, y1 - 40)), (x1, min(h - 1, y1 + 40)), (0, 0, 255), 1)

    # 이미지 크기에 맞는 글자 크기 (4K에서도 읽히게)
    fs = max(0.7, out.shape[1] / 2600.0)
    ft = max(2, int(round(fs * 2.5)))

    def _dim_line(dx0, dx1, y_dim, color, label):
        """수평 치수선 + 양끝 틱 + 라벨."""
        y_dim = int(max(20, min(h - 20, y_dim)))
        cv2.line(out, (dx0, y_dim), (dx1, y_dim), color, 2, cv2.LINE_AA)
        for xx in (dx0, dx1):
            cv2.line(out, (xx, y_dim - 12), (xx, y_dim + 12), color, 2, cv2.LINE_AA)
        (tw, _th), _b = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, ft)
        cv2.putText(
            out, label, (max(0, int(0.5 * (dx0 + dx1)) - tw // 2), max(30, y_dim - 14)),
            cv2.FONT_HERSHEY_SIMPLEX, fs, color, ft, cv2.LINE_AA,
        )

    # 밝은 코어 끝점 (권장 측정값): 초록 사각형 + 위쪽 수평 치수선
    lb = gap.get("left_end_bright") or {}
    rb = gap.get("right_end_bright") or {}
    bx0 = by0 = bx1 = by1 = None
    try:
        bx0, by0 = int(round(lb["x"])), int(round(lb["y"]))
        bx1, by1 = int(round(rb["x"])), int(round(rb["y"]))
    except Exception:
        pass
    if bx0 is not None and bx1 is not None:
        cv2.rectangle(out, (bx0 - 8, by0 - 8), (bx0 + 8, by0 + 8), (0, 255, 0), 2)
        cv2.rectangle(out, (bx1 - 8, by1 - 8), (bx1 + 8, by1 + 8), (0, 255, 0), 2)
        blabel = f'dx(bright)={gap.get("gap_bright_px")}px'
        if gap.get("gap_bright_mm") is not None:
            blabel = f'dx(bright)={gap["gap_bright_mm"]}mm ({gap.get("gap_bright_px")}px)'
        _dim_line(bx0, bx1, min(by0, by1) - 60, (0, 255, 0), blabel)

    # raw 레이저 끝: 아래쪽 수평 치수선 (같은 형식으로 통일)
    label = f'dx(raw)={gap.get("gap_px")}px'
    if gap.get("gap_mm") is not None:
        label = f'dx(raw)={gap["gap_mm"]}mm ({gap.get("gap_px")}px)'
    _dim_line(x0, x1, max(y0, y1) + 70, color_gap, label)
    return out
