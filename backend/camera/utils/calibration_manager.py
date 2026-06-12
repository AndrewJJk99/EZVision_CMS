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

    @property
    def pattern_size(self) -> Tuple[int, int]:
        return (self.config.inner_cols, self.config.inner_rows)

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

    def _find_chessboard_corners(self, gray: np.ndarray) -> Tuple[bool, Optional[np.ndarray]]:
        """조명 변화·압축 노이즈에 덜 민감하도록 CLAHE + SB 알고리즘 우선."""
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE

        if hasattr(cv2, "findChessboardCornersSB"):
            found, corners = cv2.findChessboardCornersSB(enhanced, self.pattern_size, flags)
            if found and corners is not None:
                return True, corners

        return cv2.findChessboardCorners(enhanced, self.pattern_size, flags)

    def detect_corners(
        self, image_bgr: np.ndarray, stabilize_preview: bool = False
    ) -> Tuple[bool, Optional[np.ndarray], np.ndarray]:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        found, corners = self._find_chessboard_corners(gray)

        if stabilize_preview and not found:
            self._preview_miss_count += 1
            if self._preview_miss_count <= 3 and self._last_preview_corners is not None:
                found = True
                corners = self._last_preview_corners
        elif stabilize_preview and found and corners is not None:
            self._preview_miss_count = 0
            self._last_preview_corners = corners.copy()

        annotated = image_bgr.copy()
        if found and corners is not None:
            criteria = (
                cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                30,
                0.001,
            )
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            cv2.drawChessboardCorners(annotated, self.pattern_size, corners, found)
            self.last_message = "체커보드 검출됨"
        else:
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
        found, corners, _ = self.detect_corners(image_bgr)
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
        session.last_message = "캘리브레이션 모드 시작"
        return session

    def stop(self, camera_id: int) -> CalibrationSession:
        session = self.get_session(camera_id)
        session.active = False
        session.last_message = "캘리브레이션 모드 종료"
        return session


calibration_manager = CalibrationManager()
