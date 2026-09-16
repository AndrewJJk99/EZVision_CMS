"""
체커보드 카메라 캘리브레이션 (Zhang's method / OpenCV calibrateCamera)

고도화: Brown/Rational 왜곡 모델, outlier view 제거, Pass/Fail, 샘플 품질 가이드.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# 기본: 20mm 정사각형 4x4 배치 → 내부 코너 3x3
DEFAULT_INNER_COLS = 3
DEFAULT_INNER_ROWS = 3
DEFAULT_SQUARE_MM = 20.0
MIN_SAMPLES = 8
RECOMMENDED_SAMPLES = 12

DISTORTION_MODELS = ("brown5", "rational")

# Pass/Fail 기준 (px)
RMS_PASS_PX = 0.35
RMS_WARN_PX = 0.50
MAX_VIEW_PASS_PX = 0.50
FX_FY_RATIO_MIN = 0.98
FX_FY_RATIO_MAX = 1.02
MIN_BOARD_COVERAGE = 0.25
OUTLIER_MAD_K = 2.5
# 프리뷰: 단발 검출 실패 시 이전 코너 유지 (기본 300ms×12 ≈ 3.6초, 대형 패턴은 더 길게)
PREVIEW_HOLD_FRAMES = 12
LARGE_PATTERN_CORNER_COUNT = 16  # 4×4 inner 이상
# 샘플 캡처는 원본 좌표를 저장하되, 코너 "탐색"만 이 크기 이하로 축소해 속도를 확보한다.
CAPTURE_DETECT_MAX_EDGE_PX = 1280

# ── 자동 캘리브레이션(보드 정지 감지 → 자동 채택) 파라미터
# 판정은 축소 프리뷰로, 실제 샘플은 원본 grab → add_sample (해상도/정확도 기존과 동일)
AUTO_MOTION_EPS_PX = 2.0      # 축소본 기준 평균 코너 이동량이 이 이하면 "정지"
AUTO_STILL_TICKS = 3          # 정지가 이만큼 연속되어야 채택 (모션블러 방지)
AUTO_COOLDOWN_TICKS = 4       # 채택 후 이만큼은 다시 담지 않음
AUTO_TARGET_SAMPLES = RECOMMENDED_SAMPLES  # 자동 종료 목표 샘플 수
AUTO_MIN_ZONES = 6            # 9구역 중 최소 커버 구역 수 (σ가 안 떨어질 때의 상한 보루)

# ── ROS식 4축(X/Y/Size/Skew) 다양성 판정
# 위치만이 아니라 면외 기울기(skew)까지 다양해야 σ(초점거리·주점)가 떨어진다.
PARAM_MIN_DIST = 0.18        # 기존 샘플과 4축 L1 거리가 이 이상이어야 "새로운" 포즈로 채택
XY_GOAL = 0.6                # x, y 커버리지 목표 폭
SIZE_GOAL = 0.35             # size 커버리지 목표 폭
SKEW_GOAL = 0.4              # skew 커버리지 목표 폭
MIN_SKEW_COVERAGE = 0.25     # 자동 종료 전 요구하는 최소 기울기 다양성(정면-only 완료 방지)
MIN_POS_COVERAGE = 0.4       # 자동 종료 전 요구하는 최소 위치(x·y) 다양성

# ── 증분 재계산 · 파라미터 불확실성(σ) 수렴 종료
# calibrateCameraExtended의 stdDeviationsIntrinsics로 "얼마나 확신하는가"를 판정한다.
CONV_FOCAL_REL = 0.003        # σ(fx)/fx, σ(fy)/fy 상대 임계 (0.3%)
CONV_CENTER_PX = 3.0          # σ(cx), σ(cy) 절대 임계 (px)
CONV_STABLE_ROUNDS = 2        # 연속 이 횟수 만족해야 수렴 인정
AUTO_MAX_SAMPLES = 30         # 무한 수집 방지 상한
AUTO_MIN_ZONES_CONV = 4       # σ 수렴으로 끝낼 때 요구하는 최소 구역 수


def undistort_bgr(
    image_bgr: np.ndarray,
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    distortion_model: str = "brown5",
) -> np.ndarray:
    """캘리브 JSON meta의 distortion_model에 맞게 undistort (brown5 / rational)."""
    _ = distortion_model  # rational도 동일 API, dist 계수 길이로 구분
    return cv2.undistort(image_bgr, camera_matrix, dist_coeffs)


def _calib_flags(distortion_model: str, fix_aspect_ratio: bool) -> int:
    flags = cv2.CALIB_USE_INTRINSIC_GUESS
    if distortion_model == "rational":
        flags |= cv2.CALIB_RATIONAL_MODEL
    if fix_aspect_ratio:
        flags |= cv2.CALIB_FIX_ASPECT_RATIO
    return flags


def _initial_camera_matrix(image_size: Tuple[int, int]) -> np.ndarray:
    """CALIB_USE_INTRINSIC_GUESS/FIX_ASPECT_RATIO용 초기 내부 파라미터."""
    w, h = image_size
    f = float(max(w, h))
    return np.array(
        [
            [f, 0.0, w / 2.0],
            [0.0, f, h / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _flag_names(distortion_model: str, fix_aspect_ratio: bool) -> List[str]:
    names = ["USE_INTRINSIC_GUESS"]
    if distortion_model == "rational":
        names.append("RATIONAL")
    if fix_aspect_ratio:
        names.append("FIX_ASPECT_RATIO")
    return names


def _solve_calibration(
    object_points_list: List[np.ndarray],
    image_points_list: List[np.ndarray],
    image_size: Tuple[int, int],
    distortion_model: str,
    fix_aspect_ratio: bool,
):
    """calibrateCameraExtended — 파라미터 표준편차(σ)와 뷰별 오차를 함께 반환.

    반환: (rms, K, dist, rvecs, tvecs, std_intrinsics, per_view_errors)
    std_intrinsics 순서: [fx, fy, cx, cy, k1, k2, p1, p2, k3, ...]
    """
    w, h = image_size
    flags = _calib_flags(distortion_model, fix_aspect_ratio)
    camera_matrix = _initial_camera_matrix((w, h))
    (
        rms,
        camera_matrix,
        dist_coeffs,
        rvecs,
        tvecs,
        std_intrinsics,
        _std_extrinsics,
        per_view_errors,
    ) = cv2.calibrateCameraExtended(
        object_points_list,
        image_points_list,
        (w, h),
        camera_matrix,
        None,
        flags=flags,
    )
    per_view = [float(e) for e in np.asarray(per_view_errors).reshape(-1)]
    std_flat = np.asarray(std_intrinsics, dtype=np.float64).reshape(-1)
    return rms, camera_matrix, dist_coeffs, rvecs, tvecs, std_flat, per_view


def _param_std_dict(std_flat: np.ndarray, camera_matrix: np.ndarray) -> dict:
    """σ 배열을 이름 있는 dict로 (없으면 None)."""
    def at(i):
        return float(std_flat[i]) if std_flat.size > i else None

    fx = float(camera_matrix[0, 0]) or 1.0
    fy = float(camera_matrix[1, 1]) or 1.0
    s_fx, s_fy, s_cx, s_cy = at(0), at(1), at(2), at(3)
    dist_sigmas = [v for v in (at(4), at(5), at(6), at(7), at(8)) if v is not None]
    return {
        "fx": None if s_fx is None else round(s_fx, 4),
        "fy": None if s_fy is None else round(s_fy, 4),
        "cx": None if s_cx is None else round(s_cx, 4),
        "cy": None if s_cy is None else round(s_cy, 4),
        "fx_rel": None if s_fx is None else round(s_fx / abs(fx), 6),
        "fy_rel": None if s_fy is None else round(s_fy / abs(fy), 6),
        "dist_max": round(max(dist_sigmas), 6) if dist_sigmas else None,
    }


def _confidence_from_std(param_std: dict) -> float:
    """σ 임계 대비 달성률(0~1). 가장 부족한 항목이 전체 신뢰도를 결정."""
    ratios = []
    for key, limit in (("fx_rel", CONV_FOCAL_REL), ("fy_rel", CONV_FOCAL_REL)):
        v = param_std.get(key)
        if v is not None:
            ratios.append(limit / max(v, 1e-9))
    for key in ("cx", "cy"):
        v = param_std.get(key)
        if v is not None:
            ratios.append(CONV_CENTER_PX / max(v, 1e-9))
    if not ratios:
        return 0.0
    return float(min(1.0, min(ratios)))


def _per_view_reproj_errors(
    object_points_list: List[np.ndarray],
    image_points_list: List[np.ndarray],
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    rvecs,
    tvecs,
) -> List[float]:
    errors = []
    for i in range(len(object_points_list)):
        proj, _ = cv2.projectPoints(
            object_points_list[i],
            rvecs[i],
            tvecs[i],
            camera_matrix,
            dist_coeffs,
        )
        err = cv2.norm(image_points_list[i], proj, cv2.NORM_L2) / len(proj)
        errors.append(float(err))
    return errors


def _outlier_indices(per_view_errors: List[float], min_keep: int) -> List[int]:
    if len(per_view_errors) <= min_keep:
        return []
    arr = np.array(per_view_errors, dtype=np.float64)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    sigma = max(mad * 1.4826, 0.02)
    threshold = med + OUTLIER_MAD_K * sigma
    outliers = [i for i, e in enumerate(per_view_errors) if e > threshold]
    if len(per_view_errors) - len(outliers) < min_keep:
        ranked = sorted(range(len(arr)), key=lambda i: arr[i], reverse=True)
        allow_drop = len(per_view_errors) - min_keep
        return ranked[:allow_drop]
    return outliers


def _analyze_sample_quality(
    corners: np.ndarray,
    image_size: Tuple[int, int],
    pattern_size: Tuple[int, int],
) -> dict:
    w, h = image_size
    cols, rows = pattern_size
    pts = corners.reshape(-1, 2).astype(np.float64)
    cx, cy = float(pts[:, 0].mean()), float(pts[:, 1].mean())
    zone_col = 0 if cx < w / 3 else (1 if cx < 2 * w / 3 else 2)
    zone_row = 0 if cy < h / 3 else (1 if cy < 2 * h / 3 else 2)
    zone = zone_row * 3 + zone_col

    span_x = float(pts[:, 0].max() - pts[:, 0].min())
    span_y = float(pts[:, 1].max() - pts[:, 1].min())
    coverage = max(span_x / max(w, 1), span_y / max(h, 1))

    grid = corners.reshape(rows, cols, 2)
    v = grid[0, -1, :] - grid[0, 0, :]
    tilt_deg = abs(float(np.degrees(np.arctan2(v[1], v[0]))))

    warnings: List[str] = []
    if coverage < MIN_BOARD_COVERAGE:
        warnings.append("보드가 화면 대비 너무 작습니다 (40% 이상 권장)")
    if tilt_deg < 5:
        warnings.append("기울기가 작습니다 — 보드를 더 기울여 촬영하세요")
    if zone == 4:
        warnings.append("중앙만 반복됨 — 가장자리/모서리 포즈를 추가하세요")

    return {
        "zone": zone,
        "coverage": round(coverage, 3),
        "tilt_deg": round(tilt_deg, 1),
        "center_px": {"x": round(cx, 1), "y": round(cy, 1)},
        "warnings": warnings,
    }


def _sample_params(
    corners: np.ndarray,
    image_size: Tuple[int, int],
    pattern_size: Tuple[int, int],
) -> dict:
    """ROS camera_calibration식 4축 파라미터 (모두 0~1).

    x, y   : 보드 중심 위치 (화면 비율)
    size   : 보드가 화면에서 차지하는 크기 (√넓이 / √화면넓이)
    skew   : 면외 기울기(perspective) — 정면이면 0, 기울일수록 큼.
             σ(초점거리·주점)를 낮추는 핵심 축.
    """
    w, h = image_size
    cols, rows = pattern_size
    grid = corners.reshape(rows, cols, 2).astype(np.float64)
    pts = corners.reshape(-1, 2).astype(np.float64)

    cx, cy = float(pts[:, 0].mean()), float(pts[:, 1].mean())

    up_left = grid[0, 0]
    up_right = grid[0, -1]
    down_right = grid[-1, -1]
    down_left = grid[-1, 0]

    # 외곽 사각형 넓이(shoelace) → 크기 축
    quad = np.array([up_left, up_right, down_right, down_left])
    area = 0.5 * abs(
        float(
            np.dot(quad[:, 0], np.roll(quad[:, 1], -1))
            - np.dot(quad[:, 1], np.roll(quad[:, 0], -1))
        )
    )
    size = float(np.sqrt(area) / np.sqrt(max(w * h, 1)))

    # up_right 코너의 내각이 90°에서 얼마나 벗어나는가 → 기울기 축
    def _angle(a, b, c):
        v1 = a - b
        v2 = c - b
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 < 1e-6 or n2 < 1e-6:
            return np.pi / 2.0
        cosang = float(np.dot(v1, v2) / (n1 * n2))
        return float(np.arccos(max(-1.0, min(1.0, cosang))))

    skew = min(1.0, 2.0 * abs((np.pi / 2.0) - _angle(up_left, up_right, down_right)))

    return {
        "x": round(cx / max(w, 1), 4),
        "y": round(cy / max(h, 1), 4),
        "size": round(size, 4),
        "skew": round(skew, 4),
    }


def _pose_coverage(sample_qualities: List[dict]) -> dict:
    zones = {q["zone"] for q in sample_qualities if q.get("zone") is not None}
    return {
        "zones_covered": len(zones),
        "zones_total": 9,
        "ratio": round(len(zones) / 9.0, 2),
        "missing_hint": "9구역 중 " + str(len(zones)) + "/9 커버",
    }


def _assess_quality(
    rms_error: float,
    per_view_errors: List[float],
    camera_matrix: np.ndarray,
    sample_count: int,
    pose_cov: dict,
    excluded_indices: List[int],
) -> dict:
    fx, fy = float(camera_matrix[0, 0]), float(camera_matrix[1, 1])
    fx_fy_ratio = fx / fy if fy else 1.0
    max_view = max(per_view_errors) if per_view_errors else 999.0

    issues: List[str] = []
    level = "pass"

    if rms_error > RMS_WARN_PX:
        issues.append(f"RMS {rms_error:.3f}px > {RMS_WARN_PX}px")
        level = "fail"
    elif rms_error > RMS_PASS_PX:
        issues.append(f"RMS {rms_error:.3f}px > 권장 {RMS_PASS_PX}px")
        if level == "pass":
            level = "warn"

    if max_view > MAX_VIEW_PASS_PX:
        issues.append(f"최대 뷰 오차 {max_view:.3f}px > {MAX_VIEW_PASS_PX}px")
        level = "fail"

    if not (FX_FY_RATIO_MIN <= fx_fy_ratio <= FX_FY_RATIO_MAX):
        issues.append(f"fx/fy={fx_fy_ratio:.4f} (권장 {FX_FY_RATIO_MIN}~{FX_FY_RATIO_MAX})")
        if level == "pass":
            level = "warn"

    if sample_count < RECOMMENDED_SAMPLES:
        issues.append(f"샘플 {sample_count}장 (권장 {RECOMMENDED_SAMPLES}+)")
        if level == "pass":
            level = "warn"

    if pose_cov.get("zones_covered", 0) < 5:
        issues.append(f"포즈 다양성 부족 ({pose_cov.get('missing_hint', '')})")
        if level == "pass":
            level = "warn"

    return {
        "pass": level == "pass",
        "level": level,
        "rms_px": round(float(rms_error), 4),
        "max_per_view_px": round(float(max_view), 4),
        "fx_fy_ratio": round(fx_fy_ratio, 4),
        "excluded_samples": excluded_indices,
        "excluded_count": len(excluded_indices),
        "pose_coverage": pose_cov,
        "issues": issues,
    }


@dataclass
class CalibrationConfig:
    inner_cols: int = DEFAULT_INNER_COLS
    inner_rows: int = DEFAULT_INNER_ROWS
    square_size_mm: float = DEFAULT_SQUARE_MM
    distortion_model: str = "brown5"
    fix_aspect_ratio: bool = True


@dataclass
class CalibrationSession:
    camera_id: int
    config: CalibrationConfig = field(default_factory=CalibrationConfig)
    active: bool = False
    sample_count: int = 0
    last_detected: bool = False
    last_message: str = ""
    image_size: Optional[Tuple[int, int]] = None
    camera_matrix: Optional[np.ndarray] = None
    dist_coeffs: Optional[np.ndarray] = None
    rms_error: Optional[float] = None
    per_view_errors: List[float] = field(default_factory=list)
    excluded_sample_indices: List[int] = field(default_factory=list)
    quality_report: Optional[dict] = None
    calib_flags: List[str] = field(default_factory=list)
    _sample_qualities: List[dict] = field(default_factory=list, repr=False)
    _object_points_list: List[np.ndarray] = field(default_factory=list, repr=False)
    _image_points_list: List[np.ndarray] = field(default_factory=list, repr=False)
    _preview_miss_count: int = field(default=0, repr=False)
    _last_preview_corners: Optional[np.ndarray] = field(default=None, repr=False)
    last_detection_method: str = ""
    # ── 자동 모드 상태
    auto_enabled: bool = False
    auto_done: bool = False
    auto_last_reason: str = ""
    # ── 증분 재계산 / σ 수렴
    param_std: Optional[dict] = None
    confidence: float = 0.0
    converged: bool = False
    last_calib_at_count: int = 0
    _conv_rounds: int = field(default=0, repr=False)
    _auto_prev_corners: Optional[np.ndarray] = field(default=None, repr=False)
    _auto_still_ticks: int = field(default=0, repr=False)
    _auto_cooldown: int = field(default=0, repr=False)

    @property
    def pattern_size(self) -> Tuple[int, int]:
        return (self.config.inner_cols, self.config.inner_rows)

    @property
    def _corner_count(self) -> int:
        cols, rows = self.pattern_size
        return cols * rows

    @property
    def _is_large_pattern(self) -> bool:
        return self._corner_count >= LARGE_PATTERN_CORNER_COUNT

    def _preview_hold_limit(self) -> int:
        return PREVIEW_HOLD_FRAMES + self._corner_count // 2

    # ------------------------------------------------------------------
    # 코너 검출 (OpenCV 순서를 신뢰하는 단순·견고한 파이프라인)
    # ------------------------------------------------------------------
    @staticmethod
    def _gray_variants(gray: np.ndarray) -> List[np.ndarray]:
        """원본 + CLAHE(조명 불균일·흑백 대비 보정).

        블러/업스케일은 흑백 엣지를 흐려 코너 위치를 어긋나게 하므로 사용하지 않음.
        """
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return [gray, clahe.apply(gray)]

    @staticmethod
    def _is_degenerate(corners: np.ndarray) -> bool:
        """검출 결과가 한 점/한 선에 몰려 있는 명백한 오검출인지 확인."""
        pts = corners.reshape(-1, 2).astype(np.float64)
        spread_x = float(pts[:, 0].max() - pts[:, 0].min())
        spread_y = float(pts[:, 1].max() - pts[:, 1].min())
        return spread_x < 5.0 or spread_y < 5.0

    def _validate_corners(self, corners: np.ndarray) -> bool:
        """OpenCV 순서를 신뢰하고, 명백히 깨진 검출만 거부 (원근·회전은 허용)."""
        if self._is_degenerate(corners):
            return False

        cols, rows = self.pattern_size
        objp = np.zeros((cols * rows, 2), np.float32)
        objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
        imgp = corners.reshape(-1, 2).astype(np.float32)

        H, _ = cv2.findHomography(objp, imgp, method=0)
        if H is None:
            # 호모그래피 계산이 안 되어도 OpenCV 검출 자체는 신뢰
            return True
        proj = cv2.perspectiveTransform(objp.reshape(-1, 1, 2), H).reshape(-1, 2)
        errs = np.linalg.norm(proj - imgp, axis=1)
        span = float(np.linalg.norm(imgp[0] - imgp[-1])) or 1.0
        # 관대한 임계값: 평면 격자에서 크게 벗어난 경우만 거부
        return float(np.median(errs)) <= span * 0.15

    def _estimate_square_px(self, corners: np.ndarray) -> float:
        cols, rows = self.pattern_size
        grid = corners.reshape(rows, cols, 2)
        dists: List[float] = []
        for r in range(rows):
            for c in range(cols - 1):
                dists.append(float(np.linalg.norm(grid[r, c + 1] - grid[r, c])))
        for c in range(cols):
            for r in range(rows - 1):
                dists.append(float(np.linalg.norm(grid[r + 1, c] - grid[r, c])))
        return float(np.median(dists)) if dists else 20.0

    def _subpix_window(self, corners: np.ndarray) -> Tuple[int, int]:
        """서브픽셀 창은 인접 코너를 포함하지 않도록 한 칸의 ~40%로 제한."""
        sq = self._estimate_square_px(corners)
        win = int(max(3, min(11, round(sq * 0.4))))
        win = win + 1 if win % 2 == 0 else win
        return win, win

    def _refine_corners(self, gray: np.ndarray, corners: np.ndarray) -> np.ndarray:
        """classic 검출 결과를 원본 gray에서 서브픽셀로 정밀화 (흑백 교차점)."""
        criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            50,
            0.001,
        )
        win = self._subpix_window(corners)
        return cv2.cornerSubPix(
            gray, corners.astype(np.float32), win, (-1, -1), criteria
        )

    @staticmethod
    def _resize_gray_for_detection(gray: np.ndarray, max_edge_px: int) -> Tuple[np.ndarray, float]:
        """검출용 축소 gray와 원본/축소 배율을 반환."""
        h, w = gray.shape[:2]
        max_edge = max(w, h)
        if max_edge_px <= 0 or max_edge <= max_edge_px:
            return gray, 1.0
        scale = float(max_edge_px) / float(max_edge)
        resized = cv2.resize(
            gray,
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            interpolation=cv2.INTER_AREA,
        )
        return resized, scale

    def _try_sb(
        self, image: np.ndarray
    ) -> Tuple[bool, Optional[np.ndarray], bool, str]:
        """findChessboardCornersSB: 서브픽셀 내장, 조명·엣지 변화에 강함."""
        if not hasattr(cv2, "findChessboardCornersSB"):
            return False, None, False, ""

        sb_flags = 0
        if hasattr(cv2, "CALIB_CB_NORMALIZE_IMAGE"):
            sb_flags |= cv2.CALIB_CB_NORMALIZE_IMAGE
        if hasattr(cv2, "CALIB_CB_ACCURACY"):
            sb_flags |= cv2.CALIB_CB_ACCURACY

        found, corners = cv2.findChessboardCornersSB(image, self.pattern_size, sb_flags)
        if not found or corners is None:
            return False, None, False, ""
        corners = np.asarray(corners, dtype=np.float32).reshape(-1, 1, 2)
        if corners.shape[0] != self._corner_count:
            return False, None, False, ""
        if not self._validate_corners(corners):
            return False, None, False, ""
        # SB는 이미 서브픽셀 — 추가 cornerSubPix 불필요(오히려 코너가 밀릴 수 있음)
        return True, corners, False, "findChessboardCornersSB"

    def _try_classic(
        self, image: np.ndarray
    ) -> Tuple[bool, Optional[np.ndarray], bool, str]:
        flags = (
            cv2.CALIB_CB_ADAPTIVE_THRESH
            | cv2.CALIB_CB_NORMALIZE_IMAGE
            | cv2.CALIB_CB_FAST_CHECK
        )
        found, corners = cv2.findChessboardCorners(image, self.pattern_size, flags)
        if not found or corners is None:
            return False, None, False, ""
        corners = np.asarray(corners, dtype=np.float32).reshape(-1, 1, 2)
        if corners.shape[0] != self._corner_count:
            return False, None, False, ""
        if not self._validate_corners(corners):
            return False, None, False, ""
        # classic 결과는 정수 근사 — 호출부에서 cornerSubPix 정밀화 필요
        return True, corners, True, "findChessboardCorners (classic)"

    def _find_chessboard_corners(
        self, gray: np.ndarray
    ) -> Tuple[bool, Optional[np.ndarray], bool, str]:
        """체커보드 코너 검출. 반환: (found, corners Nx1x2, needs_subpix, method).

        OpenCV가 반환하는 행-우선(row-major) 순서를 그대로 신뢰한다.
        직접 재정렬하면 대응점이 어긋나 오버레이가 삐죽해지고 캘리브레이션이 망가진다.
        """
        for image in self._gray_variants(gray):
            ok, corners, needs_subpix, method = self._try_sb(image)
            if ok:
                return ok, corners, needs_subpix, method
            ok, corners, needs_subpix, method = self._try_classic(image)
            if ok:
                return ok, corners, needs_subpix, method
        return False, None, False, ""

    # ------------------------------------------------------------------
    def _object_template(self) -> np.ndarray:
        cols, rows = self.pattern_size
        objp = np.zeros((cols * rows, 3), np.float32)
        objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
        objp *= float(self.config.square_size_mm)
        return objp

    def reset_samples(self):
        self._object_points_list.clear()
        self._image_points_list.clear()
        self._sample_qualities.clear()
        self.sample_count = 0
        self.camera_matrix = None
        self.dist_coeffs = None
        self.rms_error = None
        self.per_view_errors.clear()
        self.excluded_sample_indices.clear()
        self.quality_report = None
        self.calib_flags.clear()
        self.image_size = None
        self.auto_reset()

    def quality_guide(self) -> dict:
        pose = _pose_coverage(self._sample_qualities)
        last_warnings = (
            self._sample_qualities[-1].get("warnings", [])
            if self._sample_qualities
            else []
        )
        return {
            "sample_count": self.sample_count,
            "min_samples": MIN_SAMPLES,
            "recommended_samples": RECOMMENDED_SAMPLES,
            "pose_coverage": pose,
            "last_sample_warnings": last_warnings,
            "distortion_model": self.config.distortion_model,
        }

    def _smooth_preview_corners(
        self, corners: np.ndarray, alpha: float = 0.35
    ) -> np.ndarray:
        """프리뷰 전용 EMA 안정화 — 고정 환경에서 코너 떨림(번쩍) 억제.

        보드가 실제로 크게 움직이면 EMA 대신 즉시 새 위치로 추종한다.
        캡처(샘플 추가)에는 적용하지 않으므로 캘리브레이션 정밀도에는 영향 없음.
        """
        prev = self._last_preview_corners
        if prev is None or prev.shape != corners.shape:
            return corners
        disp = np.linalg.norm(
            corners.reshape(-1, 2) - prev.reshape(-1, 2), axis=1
        )
        sq = self._estimate_square_px(corners)
        if float(np.median(disp)) > 0.25 * sq:
            return corners
        return (alpha * corners + (1.0 - alpha) * prev).astype(np.float32)

    def detect_corners(
        self, image_bgr: np.ndarray, stabilize_preview: bool = False
    ) -> Tuple[bool, Optional[np.ndarray], np.ndarray]:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        raw_found, corners, needs_subpix, method = self._find_chessboard_corners(gray)
        found = raw_found

        if raw_found and corners is not None:
            if needs_subpix:
                corners = self._refine_corners(gray, corners)
            if stabilize_preview:
                corners = self._smooth_preview_corners(corners)
            self._preview_miss_count = 0
            self._last_preview_corners = corners.copy()
            self.last_detection_method = method

        hold_limit = self._preview_hold_limit()
        if (
            not found
            and stabilize_preview
            and self._last_preview_corners is not None
        ):
            self._preview_miss_count += 1
            if self._preview_miss_count <= hold_limit:
                found = True
                corners = self._last_preview_corners.copy()

        annotated = image_bgr.copy()
        if found and corners is not None:
            cv2.drawChessboardCorners(annotated, self.pattern_size, corners, found)
            if raw_found:
                self.last_message = f"체커보드 검출됨 ({self.last_detection_method})"
            else:
                self.last_message = "체커보드 검출 유지 (프레임 보간)"
        else:
            if stabilize_preview:
                self._preview_miss_count = hold_limit + 1
            cv2.putText(
                annotated,
                "Checkerboard NOT found",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
            self.last_message = "체커보드를 찾지 못했습니다"

        self.last_detected = bool(found)
        return found, corners, annotated

    def detect_corners_for_capture(
        self, image_bgr: np.ndarray
    ) -> Tuple[bool, Optional[np.ndarray]]:
        """샘플 캡처용 — 축소본에서 탐색 후 코너 좌표는 원본 해상도로 저장."""
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        detect_gray, scale = self._resize_gray_for_detection(gray, CAPTURE_DETECT_MAX_EDGE_PX)
        found, corners, needs_subpix, method = self._find_chessboard_corners(detect_gray)
        if not found or corners is None:
            return False, None

        if needs_subpix:
            corners = self._refine_corners(detect_gray, corners)

        if scale != 1.0:
            corners = (corners.astype(np.float32) / float(scale)).astype(np.float32)
            # 원본 전체에서 다시 찾는 것이 아니라, 축소 검출 위치 주변만 국소 보정한다.
            try:
                corners = self._refine_corners(gray, corners)
            except cv2.error:
                pass

        self._preview_miss_count = 0
        self._last_preview_corners = corners.copy()
        self.last_detection_method = (
            f"{method} @detect {detect_gray.shape[1]}x{detect_gray.shape[0]}"
            if scale != 1.0
            else method
        )
        self.last_detected = True
        self.last_message = f"체커보드 검출됨 ({self.last_detection_method})"
        return True, corners

    def preview_overlay(self, image_bgr: np.ndarray) -> Tuple[np.ndarray, dict]:
        found, _, annotated = self.detect_corners(image_bgr, stabilize_preview=True)
        info = {
            "detected": found,
            "sample_count": self.sample_count,
            "min_samples": MIN_SAMPLES,
            "active": self.active,
            "pattern_cols": self.config.inner_cols,
            "pattern_rows": self.config.inner_rows,
            "square_size_mm": self.config.square_size_mm,
            "message": self.last_message,
            "detection_method": self.last_detection_method,
            "rms_error": self.rms_error,
            "calibrated": self.camera_matrix is not None,
            "quality_guide": self.quality_guide(),
            "quality_report": self.quality_report,
            "excluded_sample_indices": self.excluded_sample_indices,
            "distortion_model": self.config.distortion_model,
            "calib_flags": self.calib_flags,
        }
        status = (
            f"Samples: {self.sample_count}/{MIN_SAMPLES}+ | "
            f"Pattern: {self.config.inner_cols}x{self.config.inner_rows} inner | "
            f"Square: {self.config.square_size_mm}mm"
        )
        cv2.putText(
            annotated,
            status,
            (20, annotated.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0) if found else (0, 165, 255),
            2,
            cv2.LINE_AA,
        )
        if self.rms_error is not None:
            cv2.putText(
                annotated,
                f"RMS reproj error: {self.rms_error:.4f} px",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )
        return annotated, info

    def add_sample(self, image_bgr: np.ndarray) -> dict:
        found, corners = self.detect_corners_for_capture(image_bgr)
        if not found or corners is None:
            return {
                "success": False,
                "message": "샘플 추가 실패: 체커보드가 검출되지 않았습니다",
                "sample_count": self.sample_count,
            }

        h, w = image_bgr.shape[:2]
        if self.image_size is None:
            self.image_size = (w, h)
        elif self.image_size != (w, h):
            return {
                "success": False,
                "message": "이미지 해상도가 이전 샘플과 다릅니다",
                "sample_count": self.sample_count,
            }

        quality = _analyze_sample_quality(corners, (w, h), self.pattern_size)
        quality["params"] = _sample_params(corners, (w, h), self.pattern_size)
        self._object_points_list.append(self._object_template())
        self._image_points_list.append(corners)
        self._sample_qualities.append(quality)
        self.sample_count += 1
        self.quality_report = None
        self.excluded_sample_indices.clear()
        msg = f"샘플 {self.sample_count}장 추가됨"
        if quality.get("warnings"):
            msg += " — " + quality["warnings"][0]
        return {
            "success": True,
            "message": msg,
            "sample_count": self.sample_count,
            "sample_quality": quality,
            "quality_guide": self.quality_guide(),
        }

    # ------------------------------------------------------------------
    # 자동 모드: 보드가 "잠깐 멈춘 순간"만 자동 채택
    # ------------------------------------------------------------------
    def auto_reset(self):
        """자동 수집 상태 초기화 (시작/종료/샘플 초기화 시)."""
        self.auto_done = False
        self.auto_last_reason = ""
        self._auto_prev_corners = None
        self._auto_still_ticks = 0
        self._auto_cooldown = 0
        self.converged = False
        self._conv_rounds = 0
        self.confidence = 0.0
        self.param_std = None
        self.last_calib_at_count = 0

    def mark_auto_accepted(self):
        """샘플이 실제로 담긴 뒤 호출 — 쿨다운 설정, 정지 카운터 리셋."""
        self._auto_cooldown = AUTO_COOLDOWN_TICKS
        self._auto_still_ticks = 0

    def zones_covered(self) -> int:
        return len({q["zone"] for q in self._sample_qualities if q.get("zone") is not None})

    def _accepted_params(self) -> List[dict]:
        return [q["params"] for q in self._sample_qualities if q.get("params")]

    def pose_axis_coverage(self) -> dict:
        """채택 샘플들의 축별 범위(max-min)/goal → {x,y,size,skew} 각 0~1."""
        params = self._accepted_params()
        goals = {"x": XY_GOAL, "y": XY_GOAL, "size": SIZE_GOAL, "skew": SKEW_GOAL}
        cov = {}
        for axis, goal in goals.items():
            if len(params) < 2:
                cov[axis] = 0.0
                continue
            vals = [p[axis] for p in params]
            spread = float(max(vals) - min(vals))
            cov[axis] = round(min(1.0, spread / max(goal, 1e-6)), 3)
        return cov

    def _pose_novelty(self, cand: dict) -> Tuple[bool, str]:
        """후보 포즈가 기존과 충분히 다른가 + 가장 부족한 축 안내.

        반환: (novel, guidance_reason)
        """
        params = self._accepted_params()
        axes = ("x", "y", "size", "skew")
        if not params:
            return True, ""

        # 1) 4축 L1 거리 최소값 — 충분히 멀면 새 포즈
        min_dist = min(
            sum(abs(cand[a] - p[a]) for a in axes) for p in params
        )
        # 2) 어느 축이든 현재 범위를 넓히면 항상 유용 (경계 샘플)
        expands = False
        for a in axes:
            vals = [p[a] for p in params]
            if cand[a] < min(vals) - 0.03 or cand[a] > max(vals) + 0.03:
                expands = True
                break
        novel = (min_dist > PARAM_MIN_DIST) or expands

        # 안내 축 선정 — 기울기는 σ를 낮추는 핵심이라, 부족하면 최우선 안내
        cov = self.pose_axis_coverage()
        if cov.get("skew", 0.0) < MIN_SKEW_COVERAGE:
            worst = "skew"
        else:
            worst = min(cov, key=cov.get)
        hint = {
            "skew": "보드를 더 기울이세요 (앞뒤·좌우로)",
            "size": "거리를 바꿔보세요 (더 가까이/멀리)",
            "x": "좌우로 더 옮기세요",
            "y": "위아래로 더 옮기세요",
        }.get(worst, "다른 자세로 옮기세요")
        return novel, hint

    def check_converged(self) -> bool:
        """파라미터 불확실성(σ)이 임계 이하로 안정됐는지 판정.

        연속 CONV_STABLE_ROUNDS회 충족해야 수렴으로 인정한다(일시적 하락 방지).
        """
        std = self.param_std or {}
        fx_rel, fy_rel = std.get("fx_rel"), std.get("fy_rel")
        s_cx, s_cy = std.get("cx"), std.get("cy")
        ok = (
            fx_rel is not None
            and fy_rel is not None
            and s_cx is not None
            and s_cy is not None
            and fx_rel <= CONV_FOCAL_REL
            and fy_rel <= CONV_FOCAL_REL
            and s_cx <= CONV_CENTER_PX
            and s_cy <= CONV_CENTER_PX
        )
        self._conv_rounds = self._conv_rounds + 1 if ok else 0
        self.converged = self._conv_rounds >= CONV_STABLE_ROUNDS
        return self.converged

    def auto_ready(self) -> bool:
        """자동 수집 종료 조건.

        ① σ 수렴 + 최소 샘플·구역 보장 (기본 경로)
        ② σ가 안 떨어져도 기존 목표(12장·6구역)를 채우면 종료 (상한 보루)
        ③ 그래도 안 끝나면 최대 샘플에서 강제 종료
        """
        cov = self.pose_axis_coverage()
        pos_ok = cov.get("x", 0.0) >= MIN_POS_COVERAGE and cov.get("y", 0.0) >= MIN_POS_COVERAGE
        skew_ok = cov.get("skew", 0.0) >= MIN_SKEW_COVERAGE
        # ① σ 수렴 + 위치·기울기 다양성 (정면-only / 한쪽 치우침 완료 방지)
        if self.converged and self.sample_count >= MIN_SAMPLES and pos_ok and skew_ok:
            return True
        # ② σ가 안 떨어져도 목표 샘플 + 다양성 충족 시 종료
        if self.sample_count >= AUTO_TARGET_SAMPLES and pos_ok and skew_ok:
            return True
        # ③ 무한 방지 상한
        return self.sample_count >= AUTO_MAX_SAMPLES

    def auto_evaluate(self, preview_bgr: np.ndarray) -> dict:
        """축소 프리뷰 1프레임으로 '지금 담을지'를 판정 (카메라 I/O 없음).

        실제 샘플은 호출부가 원본을 다시 grab해 add_sample로 담는다.
        """
        found, corners, annotated = self.detect_corners(
            preview_bgr, stabilize_preview=True
        )
        result = {
            "detected": bool(found),
            "accept": False,
            "still_ticks": self._auto_still_ticks,
            "motion_px": None,
            "zone": None,
            "reason": "",
            "annotated": annotated,
        }
        if self._auto_cooldown > 0:
            self._auto_cooldown -= 1

        if not found or corners is None:
            self._auto_still_ticks = 0
            self._auto_prev_corners = None
            result["still_ticks"] = 0
            result["reason"] = "보드 미검출"
            self.auto_last_reason = result["reason"]
            return result

        pts = corners.reshape(-1, 2).astype(np.float64)
        # 1) 정지 판정 — 이전 프레임 대비 평균 코너 이동량
        motion = None
        if (
            self._auto_prev_corners is not None
            and self._auto_prev_corners.shape == pts.shape
        ):
            motion = float(np.mean(np.linalg.norm(pts - self._auto_prev_corners, axis=1)))
            if motion <= AUTO_MOTION_EPS_PX:
                self._auto_still_ticks += 1
            else:
                self._auto_still_ticks = 0
        else:
            self._auto_still_ticks = 0
        self._auto_prev_corners = pts
        result["motion_px"] = None if motion is None else round(motion, 2)
        result["still_ticks"] = self._auto_still_ticks

        # 2) 위치·크기·품질 + 4축(X/Y/Size/Skew) 다양성 판정
        #    (축소본 기준 — 모두 화면 비율/각도라 원본과 동일)
        h, w = preview_bgr.shape[:2]
        quality = _analyze_sample_quality(corners, (w, h), self.pattern_size)
        params = _sample_params(corners, (w, h), self.pattern_size)
        result["zone"] = quality.get("zone")
        result["skew"] = params["skew"]

        quality_ok = float(quality.get("coverage") or 0.0) >= MIN_BOARD_COVERAGE
        novel, novelty_hint = self._pose_novelty(params)

        # 3) 최종 채택 판정
        if self._auto_still_ticks < AUTO_STILL_TICKS:
            result["reason"] = "이동 감지 — 보드를 잠시 멈추세요"
        elif self._auto_cooldown > 0:
            result["reason"] = "직전 샘플 후 대기 중"
        elif not quality_ok:
            result["reason"] = "보드가 화면 대비 너무 작습니다"
        elif not novel:
            result["reason"] = f"비슷한 자세 — {novelty_hint}"
        else:
            result["accept"] = True
            result["reason"] = "정지 확인 — 샘플 채택"

        self.auto_last_reason = result["reason"]
        return result

    def auto_state(self) -> dict:
        """상태 응답용 자동 모드 요약."""
        return {
            "enabled": self.auto_enabled,
            "done": self.auto_done,
            "reason": self.auto_last_reason,
            "still_ticks": self._auto_still_ticks,
            "cooldown": self._auto_cooldown,
            "sample_count": self.sample_count,
            "target_samples": AUTO_TARGET_SAMPLES,
            "max_samples": AUTO_MAX_SAMPLES,
            "zones_covered": self.zones_covered(),
            "axis_coverage": self.pose_axis_coverage(),
            "min_skew_coverage": MIN_SKEW_COVERAGE,
            "min_pos_coverage": MIN_POS_COVERAGE,
            "ready": self.auto_ready(),
            "confidence": round(self.confidence, 3),
            "converged": self.converged,
            "param_std": self.param_std,
            "rms_error": self.rms_error,
        }

    def run_calibration(self) -> dict:
        if self.sample_count < MIN_SAMPLES:
            return {
                "success": False,
                "message": f"최소 {MIN_SAMPLES}장 이상의 샘플이 필요합니다 (현재 {self.sample_count})",
            }
        if self.image_size is None:
            return {"success": False, "message": "이미지 크기 정보가 없습니다"}

        model = self.config.distortion_model
        if model not in DISTORTION_MODELS:
            return {"success": False, "message": f"지원하지 않는 왜곡 모델: {model}"}

        w, h = self.image_size
        self.calib_flags = _flag_names(model, self.config.fix_aspect_ratio)

        obj_all = self._object_points_list
        img_all = self._image_points_list

        rms, camera_matrix, dist_coeffs, rvecs, tvecs, std_flat, per_view = _solve_calibration(
            obj_all, img_all, (w, h), model, self.config.fix_aspect_ratio
        )
        all_per_view = list(per_view)
        excluded = _outlier_indices(per_view, MIN_SAMPLES)

        if excluded:
            keep = [i for i in range(len(obj_all)) if i not in excluded]
            obj_kept = [obj_all[i] for i in keep]
            img_kept = [img_all[i] for i in keep]
            rms, camera_matrix, dist_coeffs, rvecs, tvecs, std_flat, per_view = _solve_calibration(
                obj_kept, img_kept, (w, h), model, self.config.fix_aspect_ratio
            )
            excluded_map = excluded
        else:
            excluded_map = []
            all_per_view = list(per_view)

        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.rms_error = float(rms)
        self.per_view_errors = per_view
        self.excluded_sample_indices = excluded_map
        # 파라미터 불확실성(σ)과 신뢰도 — 증분 재계산 시 게이지/수렴 판정에 사용
        self.param_std = _param_std_dict(std_flat, camera_matrix)
        self.confidence = _confidence_from_std(self.param_std)
        self.last_calib_at_count = self.sample_count

        pose_cov = _pose_coverage(self._sample_qualities)
        self.quality_report = _assess_quality(
            self.rms_error,
            self.per_view_errors,
            camera_matrix,
            self.sample_count,
            pose_cov,
            excluded_map,
        )
        self.quality_report["param_std"] = self.param_std
        self.quality_report["confidence"] = round(self.confidence, 3)

        fx, fy = camera_matrix[0, 0], camera_matrix[1, 1]
        cx, cy = camera_matrix[0, 2], camera_matrix[1, 2]
        q = self.quality_report
        level = q.get("level", "pass")
        msg = f"캘리브레이션 완료 (Zhang / {model}) — {level.upper()}"
        if excluded_map:
            msg += f" | outlier {len(excluded_map)}장 제외"

        return {
            "success": True,
            "message": msg,
            "rms_error": self.rms_error,
            "per_view_errors": self.per_view_errors,
            "all_per_view_errors": all_per_view,
            "excluded_sample_indices": excluded_map,
            "camera_matrix": camera_matrix.tolist(),
            "dist_coeffs": dist_coeffs.reshape(-1).tolist(),
            "focal_length_px": {"fx": float(fx), "fy": float(fy)},
            "principal_point_px": {"cx": float(cx), "cy": float(cy)},
            "image_size": {"width": w, "height": h},
            "sample_count": self.sample_count,
            "distortion_model": model,
            "calib_flags": self.calib_flags,
            "quality_report": self.quality_report,
            "quality_guide": self.quality_guide(),
            "param_std": self.param_std,
            "confidence": round(self.confidence, 3),
            "converged": self.converged,
        }

    def save(self, base_dir: str, force: bool = False) -> str:
        if self.camera_matrix is None or self.dist_coeffs is None:
            raise ValueError("캘리브레이션 결과가 없습니다")
        if self.quality_report and not self.quality_report.get("pass") and not force:
            raise ValueError(
                "품질 검증 FAIL/WARN — 저장하려면 force=true 또는 UI에서 강제 저장을 선택하세요"
            )

        os.makedirs(base_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        npz_path = os.path.join(base_dir, f"camera_{self.camera_id}_calib_{stamp}.npz")
        json_path = os.path.join(base_dir, f"camera_{self.camera_id}_calib_{stamp}.json")

        np.savez(
            npz_path,
            camera_matrix=self.camera_matrix,
            dist_coeffs=self.dist_coeffs,
            image_width=self.image_size[0],
            image_height=self.image_size[1],
            pattern_cols=self.config.inner_cols,
            pattern_rows=self.config.inner_rows,
            square_size_mm=self.config.square_size_mm,
            rms_error=self.rms_error,
            distortion_model=self.config.distortion_model,
        )

        meta = {
            "camera_id": self.camera_id,
            "ui_camera_id": self.camera_id + 1,
            "method": "Zhang (OpenCV calibrateCamera)",
            "distortion_model": self.config.distortion_model,
            "calib_flags": self.calib_flags,
            "fix_aspect_ratio": self.config.fix_aspect_ratio,
            "pattern_inner_corners": list(self.pattern_size),
            "square_size_mm": self.config.square_size_mm,
            "sample_count": self.sample_count,
            "rms_error": self.rms_error,
            "per_view_errors": self.per_view_errors,
            "excluded_sample_indices": self.excluded_sample_indices,
            "camera_matrix": self.camera_matrix.tolist(),
            "dist_coeffs": self.dist_coeffs.reshape(-1).tolist(),
            "image_size": {"width": self.image_size[0], "height": self.image_size[1]},
            "quality": self.quality_report,
            "saved_at": stamp,
            "npz_path": npz_path,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        return json_path


class CalibrationManager:
    def __init__(self):
        self._sessions: Dict[int, CalibrationSession] = {}

    def get_session(self, camera_id: int) -> CalibrationSession:
        if camera_id not in self._sessions:
            self._sessions[camera_id] = CalibrationSession(camera_id=camera_id)
        return self._sessions[camera_id]

    def start(self, camera_id: int, config: Optional[CalibrationConfig] = None) -> CalibrationSession:
        session = self.get_session(camera_id)
        if config:
            session.config = config
        session.active = True
        session.reset_samples()
        session._preview_miss_count = 0
        session._last_preview_corners = None
        session.auto_enabled = False
        session.last_message = "캘리브레이션 모드 시작"
        return session

    def stop(self, camera_id: int) -> CalibrationSession:
        session = self.get_session(camera_id)
        session.active = False
        session.auto_enabled = False
        session.auto_reset()
        session.last_message = "캘리브레이션 모드 종료"
        return session


calibration_manager = CalibrationManager()
