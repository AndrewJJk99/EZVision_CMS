"""
체커보드 카메라 캘리브레이션 (Zhang's method / OpenCV calibrateCamera)
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
# 프리뷰: 단발 검출 실패 시 이전 코너 유지 (기본 300ms×12 ≈ 3.6초, 대형 패턴은 더 길게)
PREVIEW_HOLD_FRAMES = 12
LARGE_PATTERN_CORNER_COUNT = 16  # 4×4 inner 이상
# 코너 검출·서브픽셀 정밀화용 해상도 상한 (캡처)
CAPTURE_MAX_EDGE_PX = 4096


@dataclass
class CalibrationConfig:
    inner_cols: int = DEFAULT_INNER_COLS
    inner_rows: int = DEFAULT_INNER_ROWS
    square_size_mm: float = DEFAULT_SQUARE_MM


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
    _object_points_list: List[np.ndarray] = field(default_factory=list, repr=False)
    _image_points_list: List[np.ndarray] = field(default_factory=list, repr=False)
    _preview_miss_count: int = field(default=0, repr=False)
    _last_preview_corners: Optional[np.ndarray] = field(default=None, repr=False)
    last_detection_method: str = ""

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
        self.sample_count = 0
        self.camera_matrix = None
        self.dist_coeffs = None
        self.rms_error = None
        self.per_view_errors.clear()
        self.image_size = None

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
        """샘플 캡처용 — 프리뷰 보간 없이 현재 프레임에서만 검출."""
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        found, corners, needs_subpix, method = self._find_chessboard_corners(gray)
        if not found or corners is None:
            return False, None

        if needs_subpix:
            corners = self._refine_corners(gray, corners)

        self._preview_miss_count = 0
        self._last_preview_corners = corners.copy()
        self.last_detection_method = method
        self.last_detected = True
        self.last_message = f"체커보드 검출됨 ({method})"
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

        self._object_points_list.append(self._object_template())
        self._image_points_list.append(corners)
        self.sample_count += 1
        return {
            "success": True,
            "message": f"샘플 {self.sample_count}장 추가됨",
            "sample_count": self.sample_count,
        }

    def run_calibration(self) -> dict:
        if self.sample_count < MIN_SAMPLES:
            return {
                "success": False,
                "message": f"최소 {MIN_SAMPLES}장 이상의 샘플이 필요합니다 (현재 {self.sample_count})",
            }
        if self.image_size is None:
            return {"success": False, "message": "이미지 크기 정보가 없습니다"}

        w, h = self.image_size
        rms, camera_matrix, dist_coeffs, _rvecs, _tvecs = cv2.calibrateCamera(
            self._object_points_list,
            self._image_points_list,
            (w, h),
            None,
            None,
        )

        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.rms_error = float(rms)

        self.per_view_errors = []
        for i in range(len(self._object_points_list)):
            proj, _ = cv2.projectPoints(
                self._object_points_list[i],
                _rvecs[i],
                _tvecs[i],
                camera_matrix,
                dist_coeffs,
            )
            err = cv2.norm(self._image_points_list[i], proj, cv2.NORM_L2) / len(proj)
            self.per_view_errors.append(float(err))

        fx, fy = camera_matrix[0, 0], camera_matrix[1, 1]
        cx, cy = camera_matrix[0, 2], camera_matrix[1, 2]
        return {
            "success": True,
            "message": "캘리브레이션 완료 (Zhang's method)",
            "rms_error": self.rms_error,
            "per_view_errors": self.per_view_errors,
            "camera_matrix": camera_matrix.tolist(),
            "dist_coeffs": dist_coeffs.reshape(-1).tolist(),
            "focal_length_px": {"fx": float(fx), "fy": float(fy)},
            "principal_point_px": {"cx": float(cx), "cy": float(cy)},
            "image_size": {"width": w, "height": h},
            "sample_count": self.sample_count,
        }

    def save(self, base_dir: str) -> str:
        if self.camera_matrix is None or self.dist_coeffs is None:
            raise ValueError("캘리브레이션 결과가 없습니다")

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
        )

        meta = {
            "camera_id": self.camera_id,
            "ui_camera_id": self.camera_id + 1,
            "method": "Zhang (OpenCV calibrateCamera)",
            "pattern_inner_corners": list(self.pattern_size),
            "square_size_mm": self.config.square_size_mm,
            "sample_count": self.sample_count,
            "rms_error": self.rms_error,
            "per_view_errors": self.per_view_errors,
            "camera_matrix": self.camera_matrix.tolist(),
            "dist_coeffs": self.dist_coeffs.reshape(-1).tolist(),
            "image_size": {"width": self.image_size[0], "height": self.image_size[1]},
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
        session.last_message = "캘리브레이션 모드 시작"
        return session

    def stop(self, camera_id: int) -> CalibrationSession:
        session = self.get_session(camera_id)
        session.active = False
        session.last_message = "캘리브레이션 모드 종료"
        return session


calibration_manager = CalibrationManager()
