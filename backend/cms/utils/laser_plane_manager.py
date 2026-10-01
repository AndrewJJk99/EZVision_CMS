# -*- coding: utf-8 -*-
"""레이저 광평면(light-plane) 3D 캘리브레이션 — 코어 기하 (Step 1).

기존 calibration/measurement 코드와 **완전히 분리**된 실험 모듈이다. 여기서는
카메라 내부파라미터(K, dist)가 주어졌다는 전제 하에 다음을 제공한다:

  1) 체커보드 코너 → 보드 평면(카메라 좌표계)         : plane_from_board_pose / solve_board_pose
  2) 픽셀(u,v) → 카메라 원점에서의 3D 광선            : pixel_to_rays
  3) 광선 ∩ 평면 → 3D 점                              : intersect_rays_plane
  4) 여러 자세의 레이저 3D 점 → 광평면 피팅(SVD)       : fit_plane_svd
  5) 저장/로드된 광평면으로 픽셀 → 3D 복원             : LaserPlaneModel

핵심 아이디어: 레이저 자체(길이·각도·높이)는 미지수이며, "이미 아는 평면"인
체커보드를 3D 자(ruler)로 써서 레이저 점의 실제 3D 좌표를 얻고, 그것들을 모아
레이저 평면 (n·X + d = 0)을 복원한다.

이 파일은 단독 실행 시 합성(synthetic) 자체검증을 수행한다:
    python laser_plane_manager.py
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import cv2
import numpy as np

Plane = Tuple[np.ndarray, float]  # (n[3], d) : n·X + d = 0


# ─────────────────────────────────────────────────────────────
# 체커보드 → 평면
# ─────────────────────────────────────────────────────────────
def make_object_points(inner_cols: int, inner_rows: int, square_mm: float) -> np.ndarray:
    """체커보드 내부 코너의 보드 좌표계 3D 점 (Z=0 평면). 단위 mm."""
    cols, rows = int(inner_cols), int(inner_rows)
    objp = np.zeros((rows * cols, 3), np.float64)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * float(square_mm)
    return objp


def solve_board_pose(
    object_points: np.ndarray,
    image_points: np.ndarray,
    K: np.ndarray,
    dist: np.ndarray,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """코너 대응으로 보드 자세(rvec, tvec)를 구한다 (solvePnP)."""
    objp = np.asarray(object_points, np.float64).reshape(-1, 1, 3)
    imgp = np.asarray(image_points, np.float64).reshape(-1, 1, 2)
    ok, rvec, tvec = cv2.solvePnP(objp, imgp, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return None
    return rvec, tvec


def plane_from_board_pose(rvec: np.ndarray, tvec: np.ndarray) -> Plane:
    """보드 자세 → 카메라 좌표계에서의 보드 평면 (n·X + d = 0).

    보드 평면은 보드 좌표계의 Z=0 이므로, 평면의 법선은 보드 +Z축을 카메라
    좌표계로 회전한 것(=R의 3번째 열), 평면 위의 한 점은 t(원점의 상)이다.
    """
    R, _ = cv2.Rodrigues(np.asarray(rvec, np.float64).reshape(3, 1))
    t = np.asarray(tvec, np.float64).reshape(3)
    n = R[:, 2].astype(np.float64)
    n = n / np.linalg.norm(n)
    d = -float(n @ t)
    return n, d


# ─────────────────────────────────────────────────────────────
# 픽셀 → 광선 → 평면 교차
# ─────────────────────────────────────────────────────────────
def pixel_to_rays(uv: np.ndarray, K: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """픽셀 (u,v)들을 카메라 원점에서 나가는 3D 광선 방향으로 변환.

    undistortPoints로 왜곡을 제거한 정규화 좌표(x', y')를 얻고, z=1을 붙여
    방향벡터 (x', y', 1)로 만든다. (정규화 안 함 — 교차식에서 스케일 상쇄)
    """
    pts = np.asarray(uv, np.float64).reshape(-1, 1, 2)
    norm = cv2.undistortPoints(pts, K, dist).reshape(-1, 2)
    return np.hstack([norm, np.ones((norm.shape[0], 1))])


def intersect_rays_plane(rays: np.ndarray, plane: Plane) -> np.ndarray:
    """카메라 원점에서 나가는 광선들과 평면의 교차점 3D 좌표.

    광선 X = s·dir (원점 0), 평면 n·X + d = 0 → s = -d / (n·dir).
    n·dir ≈ 0 (광선이 평면과 평행)이면 NaN.
    """
    n, d = plane
    n = np.asarray(n, np.float64).reshape(3)
    denom = np.asarray(rays, np.float64) @ n
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(np.abs(denom) < 1e-9, np.nan, -float(d) / denom)
    return np.asarray(rays, np.float64) * s[:, None]


def board_points_to_3d(
    uv: np.ndarray, board_plane: Plane, K: np.ndarray, dist: np.ndarray
) -> np.ndarray:
    """보드 위에 찍힌 픽셀들을 보드 평면과 교차시켜 3D로 복원."""
    return intersect_rays_plane(pixel_to_rays(uv, K, dist), board_plane)


# ─────────────────────────────────────────────────────────────
# 보드 영역 마스크 (보드 위 레이저 구간만 사용)
# ─────────────────────────────────────────────────────────────
def board_quad_from_corners(corners: np.ndarray, inner_cols: int, inner_rows: int) -> np.ndarray:
    """내부 코너 격자의 네 꼭짓점(대략 보드 사각형)."""
    grid = np.asarray(corners, np.float64).reshape(int(inner_rows), int(inner_cols), 2)
    return np.array([grid[0, 0], grid[0, -1], grid[-1, -1], grid[-1, 0]], np.float32)


def filter_points_in_quad(uv: np.ndarray, quad: np.ndarray, margin: float = 0.0) -> np.ndarray:
    """사각형(볼록) 내부에 있는 (u,v)만 남긴다. margin>0이면 바깥으로 조금 확장."""
    uv = np.asarray(uv, np.float64).reshape(-1, 2)
    poly = np.asarray(quad, np.float32).reshape(-1, 1, 2)
    keep = np.zeros(len(uv), bool)
    for i, (x, y) in enumerate(uv):
        keep[i] = cv2.pointPolygonTest(poly, (float(x), float(y)), True) >= -abs(margin)
    return uv[keep]


# ─────────────────────────────────────────────────────────────
# 평면 피팅 (SVD)
# ─────────────────────────────────────────────────────────────
def fit_plane_svd(points3d: np.ndarray) -> Optional[dict]:
    """3D 점들에 최소자승 평면 피팅. n·X + d = 0, |n|=1."""
    P = np.asarray(points3d, np.float64)
    P = P[np.isfinite(P).all(axis=1)]
    if len(P) < 3:
        return None
    centroid = P.mean(axis=0)
    _u, s, vt = np.linalg.svd(P - centroid)
    n = vt[-1]
    n = n / np.linalg.norm(n)
    d = -float(n @ centroid)
    resid = np.abs(P @ n + d)
    return {
        "n": n,
        "d": d,
        "rms": float(np.sqrt(np.mean(resid**2))),
        "max": float(resid.max()),
        "n_points": int(len(P)),
        "singular_values": [float(x) for x in s],
        "centroid": centroid,
    }


# 광평면 퇴화(degenerate) 판정 임계값 — 합성 검증으로 정함.
#   레이저 3D 점이 2D 면을 못 채우고 거의 한 직선이면, 그 직선을 지나는 평면이
#   무수히 많아 법선이 엉뚱하게 결정된다(측정 시 거리 발산·비단조).
#   판별자 s2/s1(평면성): 정상 ≤0.06, 퇴화(직선) ≈0.96 → 0.10에서 큰 마진으로 갈림.
PLANE_PLANARITY_MAX = 0.10   # s2/s1 (2번째 퍼짐 대비 두께). 초과 → 퇴화(직선)
PLANE_SPREAD_MIN = 0.010     # s1/s0 (2D 퍼짐). 미만 → 사실상 1D
PLANE_SPREAD_WARN = 0.05     # 이 미만이면 약한 캘리브(경고, 저장은 허용)


def plane_health(fit: dict) -> dict:
    """평면 피팅의 건전성 지표 + 퇴화 여부. fit=fit_plane_svd(...) 결과."""
    sv = fit.get("singular_values") or []
    s0 = float(sv[0]) if len(sv) > 0 else 0.0
    s1 = float(sv[1]) if len(sv) > 1 else 0.0
    s2 = float(sv[2]) if len(sv) > 2 else 0.0
    spread = (s1 / s0) if s0 > 1e-9 else 0.0        # 2D 퍼짐(작을수록 직선)
    planarity = (s2 / s1) if s1 > 1e-9 else 1.0     # 두께/2D폭(클수록 1D)
    nz = abs(float(np.asarray(fit["n"], float).reshape(3)[2]))
    reasons = []
    if planarity > PLANE_PLANARITY_MAX:
        reasons.append(f"점들이 거의 한 직선(평면성 {planarity:.3f} > {PLANE_PLANARITY_MAX})")
    if spread < PLANE_SPREAD_MIN:
        reasons.append(f"레이저 점이 2D로 퍼지지 않음(퍼짐비 {spread:.4f} < {PLANE_SPREAD_MIN})")
    return {
        "spread_ratio": round(spread, 4),
        "planarity": round(planarity, 5),
        "n_z": round(nz, 4),
        "singular_values": [round(s0, 3), round(s1, 3), round(s2, 3)],
        "degenerate": bool(reasons),
        "reasons": reasons,
        "weak": bool(spread < PLANE_SPREAD_WARN and not reasons),
    }


# ─────────────────────────────────────────────────────────────
# 광평면 모델 (저장/로드/복원)
# ─────────────────────────────────────────────────────────────
@dataclass
class LaserPlaneModel:
    n: np.ndarray             # 평면 법선 (단위벡터)
    d: float                  # n·X + d = 0
    K: np.ndarray             # 카메라 행렬 3x3
    dist: np.ndarray          # 왜곡계수
    meta: dict = field(default_factory=dict)

    def reconstruct(self, uv: np.ndarray) -> np.ndarray:
        """레이저 픽셀 (u,v) → 카메라 좌표계 3D 점 (mm). 광선 ∩ 광평면."""
        return intersect_rays_plane(pixel_to_rays(uv, self.K, self.dist), (self.n, self.d))

    def to_json(self) -> dict:
        return {
            "type": "laser_plane",
            "version": 1,
            "plane": {"n": [float(x) for x in self.n], "d": float(self.d)},
            "camera_matrix": np.asarray(self.K, float).tolist(),
            "dist_coeffs": np.asarray(self.dist, float).reshape(-1).tolist(),
            "meta": self.meta,
        }

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)
        return path

    @staticmethod
    def load(path: str) -> "LaserPlaneModel":
        with open(path, "r", encoding="utf-8") as f:
            j = json.load(f)
        return LaserPlaneModel(
            n=np.asarray(j["plane"]["n"], np.float64),
            d=float(j["plane"]["d"]),
            K=np.asarray(j["camera_matrix"], np.float64),
            dist=np.asarray(j["dist_coeffs"], np.float64),
            meta=j.get("meta", {}),
        )


# ─────────────────────────────────────────────────────────────
# 캘리브레이션 세션 (여러 자세 누적 → 광평면 피팅 → 측정)
# ─────────────────────────────────────────────────────────────
@dataclass
class PoseSample:
    n_corners: int
    n_laser_onboard: int
    board_z_mm: float
    points3d: np.ndarray


class LaserPlaneSession:
    """카메라별 광평면 캘리브레이션 상태. 자세별로 (코너, 레이저픽셀)을 받아
    보드 위 레이저의 3D 점을 누적하고, 모이면 광평면을 피팅한다.

    detection(코너·레이저 검출)은 라우터가 담당하고, 여기서는 3D 기하만 다룬다.
    """

    def __init__(
        self,
        camera_id: int,
        inner_cols: int,
        inner_rows: int,
        square_mm: float,
        K: np.ndarray,
        dist: np.ndarray,
        calibration_file: Optional[str] = None,
    ):
        self.camera_id = int(camera_id)
        self.inner_cols = int(inner_cols)
        self.inner_rows = int(inner_rows)
        self.square_mm = float(square_mm)
        self.K = np.asarray(K, np.float64)
        self.dist = np.asarray(dist, np.float64)
        self.calibration_file = calibration_file
        self.objp = make_object_points(inner_cols, inner_rows, square_mm)
        self.samples: List[PoseSample] = []
        self.model: Optional[LaserPlaneModel] = None
        self.fit_info: Optional[dict] = None
        self.last_onboard_uv: Optional[np.ndarray] = None  # 마지막 캡처의 보드 위 레이저 픽셀(오버레이용)
        self.last_message = "세션 시작 — 보드+레이저 자세를 캡처하세요"

    # ── 자세 1개 적립 ──
    def add_pose(self, corners: np.ndarray, laser_uv: np.ndarray, min_onboard: int = 8) -> dict:
        pose = solve_board_pose(self.objp, corners, self.K, self.dist)
        if pose is None:
            return {"ok": False, "error": "보드 자세 계산 실패(solvePnP)"}
        rvec, tvec = pose
        board_plane = plane_from_board_pose(rvec, tvec)

        laser_uv = np.asarray(laser_uv, np.float64).reshape(-1, 2)
        if len(laser_uv) == 0:
            return {"ok": False, "error": "레이저 점이 없습니다"}

        quad = board_quad_from_corners(corners, self.inner_cols, self.inner_rows)
        # 보드 안쪽 코너 사각형 + 여유(테두리 칸까지) → 배경 레이저는 배제
        diag = float(np.linalg.norm(quad[0] - quad[2]))
        onboard = filter_points_in_quad(laser_uv, quad, margin=0.12 * diag)
        if len(onboard) < min_onboard:
            return {
                "ok": False,
                "error": f"보드 위 레이저 점이 너무 적습니다({len(onboard)}). 레이저가 보드에 걸치는지 확인",
                "n_laser": int(len(laser_uv)),
                "n_onboard": int(len(onboard)),
            }

        pts3d = board_points_to_3d(onboard, board_plane, self.K, self.dist)
        finite = np.isfinite(pts3d).all(axis=1)
        pts3d = pts3d[finite]
        self.last_onboard_uv = onboard[finite]  # 오버레이용 (실제 3D로 쓴 보드 위 픽셀)
        board_z = float(np.asarray(tvec).ravel()[2])
        self.samples.append(
            PoseSample(int(len(corners)), int(len(pts3d)), board_z, pts3d)
        )
        self.last_message = f"자세 {len(self.samples)} 적립 (보드 위 레이저 {len(pts3d)}점, Z≈{board_z:.0f}mm)"
        return {
            "ok": True,
            "pose_index": len(self.samples),
            "n_onboard": int(len(pts3d)),
            "board_z_mm": round(board_z, 1),
            "total_points": int(sum(s.n_laser_onboard for s in self.samples)),
        }

    # ── 피팅 ──
    def fit(self) -> dict:
        if len(self.samples) < 2:
            return {"ok": False, "error": "자세가 2개 미만입니다(권장 6~12). 더 캡처하세요"}
        pts = np.vstack([s.points3d for s in self.samples])
        fit = fit_plane_svd(pts)
        if fit is None:
            return {"ok": False, "error": "평면 피팅 실패(점 부족)"}
        self.fit_info = fit
        self.model = LaserPlaneModel(
            n=fit["n"],
            d=fit["d"],
            K=self.K,
            dist=self.dist,
            meta={
                "camera_id": self.camera_id,
                "calibration_file": self.calibration_file,
                "n_poses": len(self.samples),
                "n_points": fit["n_points"],
                "fit_rms_mm": round(fit["rms"], 4),
                "fit_max_mm": round(fit["max"], 4),
                "board_z_mm": [round(s.board_z_mm, 1) for s in self.samples],
                "square_size_mm": self.square_mm,
                "pattern_inner_corners": [self.inner_cols, self.inner_rows],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        # 자세 간 깊이 스프레드(평면이 잘 구속됐는지 지표)
        zs = [s.board_z_mm for s in self.samples]
        self.last_message = f"피팅 완료 — RMS {fit['rms']:.3f}mm ({len(self.samples)}자세, {fit['n_points']}점)"
        return {
            "ok": True,
            "rms_mm": round(fit["rms"], 4),
            "max_mm": round(fit["max"], 4),
            "n_points": fit["n_points"],
            "n_poses": len(self.samples),
            "depth_span_mm": round(float(max(zs) - min(zs)), 1) if zs else 0.0,
        }

    # ── 측정: 두 점의 3D 및 거리 ──
    def measure_points(self, uv_a, uv_b) -> dict:
        if self.model is None:
            return {"ok": False, "error": "광평면이 아직 없습니다. 먼저 캘리브레이션(피팅/로드)하세요"}
        A = self.model.reconstruct(np.asarray(uv_a, np.float64).reshape(1, 2))[0]
        B = self.model.reconstruct(np.asarray(uv_b, np.float64).reshape(1, 2))[0]
        if not (np.isfinite(A).all() and np.isfinite(B).all()):
            return {"ok": False, "error": "3D 복원 실패(광선이 평면과 평행)"}
        delta = B - A
        return {
            "ok": True,
            "point_a_mm": [round(float(x), 3) for x in A],
            "point_b_mm": [round(float(x), 3) for x in B],
            "distance_mm": round(float(np.linalg.norm(delta)), 4),
            "delta_mm": {"x": round(float(delta[0]), 4), "y": round(float(delta[1]), 4), "z": round(float(delta[2]), 4)},
        }

    def reset(self):
        self.samples.clear()
        self.model = None
        self.fit_info = None
        self.last_message = "세션 초기화됨"

    def status(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "ui_camera_id": self.camera_id + 1,
            "pattern_inner_corners": [self.inner_cols, self.inner_rows],
            "square_size_mm": self.square_mm,
            "calibration_file": self.calibration_file,
            "n_poses": len(self.samples),
            "poses": [
                {"index": i + 1, "n_onboard": s.n_laser_onboard, "board_z_mm": round(s.board_z_mm, 1)}
                for i, s in enumerate(self.samples)
            ],
            "total_points": int(sum(s.n_laser_onboard for s in self.samples)),
            "fitted": self.model is not None,
            "fit": (
                {
                    "rms_mm": round(self.fit_info["rms"], 4),
                    "max_mm": round(self.fit_info["max"], 4),
                    "n_points": self.fit_info["n_points"],
                }
                if self.fit_info
                else None
            ),
            "message": self.last_message,
        }


# ─────────────────────────────────────────────────────────────
# 통합 세션 — 내부파라미터(K·왜곡) + 광평면을 한 번의 촬영으로
# ─────────────────────────────────────────────────────────────
@dataclass
class CombinedPose:
    corners: np.ndarray   # (N,2) 체커보드 코너 (OFF 프레임)
    laser_uv: np.ndarray  # (M,2) 레이저 픽셀 (ON 프레임)


class LaserPlaneCombinedSession:
    """OFF(코너)/ON(레이저) 자세들을 모아, calibrateCamera로 내부파라미터를
    구하고 그 자세들로 광평면까지 한 번에 피팅한다. (내부파라미터 재사용 불필요)

    자세마다: add_off(코너) → add_on(레이저) 로 1자세 확정. 보드는 두 프레임 사이
    고정. 마지막에 fit()으로 K·왜곡 + 광평면을 계산한다.
    """

    def __init__(self, camera_id, inner_cols, inner_rows, square_mm, image_size):
        self.camera_id = int(camera_id)
        self.inner_cols = int(inner_cols)
        self.inner_rows = int(inner_rows)
        self.square_mm = float(square_mm)
        self.image_size = (int(image_size[0]), int(image_size[1]))
        self.objp = make_object_points(inner_cols, inner_rows, square_mm)
        self.pending_corners: Optional[np.ndarray] = None
        self.poses: List[CombinedPose] = []
        self.K: Optional[np.ndarray] = None
        self.dist: Optional[np.ndarray] = None
        self.intrinsic_rms: Optional[float] = None
        self.plane_fit: Optional[dict] = None
        self.model: Optional[LaserPlaneModel] = None
        self.last_onboard_uv: Optional[np.ndarray] = None
        self.last_message = "통합 세션 시작 — 자세마다 OFF(코너)/ON(레이저) 캡처"

    def add_off(self, corners: np.ndarray) -> dict:
        c = np.asarray(corners, np.float64).reshape(-1, 2)
        if len(c) != self.inner_cols * self.inner_rows:
            return {"ok": False, "error": f"코너 수 불일치({len(c)} != {self.inner_cols*self.inner_rows})"}
        self.pending_corners = c
        self.last_message = f"OFF 캡처됨(코너 {len(c)}) — 레이저 켜고 ON 캡처하세요"
        return {"ok": True, "pending": True, "n_corners": int(len(c))}

    def add_on(self, laser_uv: np.ndarray) -> dict:
        if self.pending_corners is None:
            return {"ok": False, "error": "먼저 OFF(코너)를 캡처하세요"}
        laser = np.asarray(laser_uv, np.float64).reshape(-1, 2)
        if len(laser) < 8:
            return {"ok": False, "error": f"레이저 점이 너무 적습니다({len(laser)})"}
        # 보드 위 레이저만(오버레이 표시용) — 실제 3D는 fit에서 계산
        quad = board_quad_from_corners(self.pending_corners, self.inner_cols, self.inner_rows)
        diag = float(np.linalg.norm(quad[0] - quad[2]))
        self.last_onboard_uv = filter_points_in_quad(laser, quad, margin=0.12 * diag)
        self.poses.append(CombinedPose(self.pending_corners, laser))
        self.pending_corners = None
        self.last_message = f"자세 {len(self.poses)} 확정 (레이저 {len(laser)}점, 보드위 {len(self.last_onboard_uv)})"
        return {"ok": True, "pose_index": len(self.poses), "n_laser": int(len(laser)),
                "n_onboard": int(len(self.last_onboard_uv))}

    def fit(self, min_poses: int = 4) -> dict:
        if len(self.poses) < min_poses:
            return {"ok": False, "error": f"자세가 {min_poses}개 미만입니다(권장 8~15). 더 캡처하세요"}
        objpoints = [self.objp.astype(np.float32) for _ in self.poses]
        imgpoints = [p.corners.astype(np.float32).reshape(-1, 1, 2) for p in self.poses]
        rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, self.image_size, None, None)
        self.K, self.dist, self.intrinsic_rms = K, dist, float(rms)

        allpts, per_pose = [], []
        for p, rvec, tvec in zip(self.poses, rvecs, tvecs):
            plane = plane_from_board_pose(rvec, tvec)
            quad = board_quad_from_corners(p.corners, self.inner_cols, self.inner_rows)
            diag = float(np.linalg.norm(quad[0] - quad[2]))
            onboard = filter_points_in_quad(p.laser_uv, quad, margin=0.12 * diag)
            z = float(np.asarray(tvec).ravel()[2])
            if len(onboard) < 8:
                per_pose.append({"board_z_mm": round(z, 1), "n_onboard": 0})
                continue
            pts3d = board_points_to_3d(onboard, plane, K, dist)
            pts3d = pts3d[np.isfinite(pts3d).all(axis=1)]
            allpts.append(pts3d)
            per_pose.append({"board_z_mm": round(z, 1), "n_onboard": int(len(pts3d))})
        if not allpts:
            return {"ok": False, "error": "보드 위 레이저 점이 없습니다(레이저가 보드에 걸치는지 확인)",
                    "intrinsic_rms_px": round(float(rms), 4)}
        pts = np.vstack(allpts)
        fit = fit_plane_svd(pts)
        self.plane_fit = fit
        zs = [pp["board_z_mm"] for pp in per_pose]
        depth_span = round(float(max(zs) - min(zs)), 1) if zs else 0.0

        # ── 퇴화(degenerate) 광평면 감지 ──────────────────────────
        # 레이저 3D 점이 2D 면을 못 채우고 거의 한 직선이면 평면이 유일하게
        # 결정되지 않아 법선이 엉뚱하게 나온다(측정 시 거리 발산·비단조).
        # 이런 평면은 저장 후 측정을 망치므로 모델을 만들지 않고 거부한다.
        health = plane_health(fit)
        health["depth_span_mm"] = depth_span
        if health["degenerate"]:
            self.model = None
            self.last_message = "광평면 퇴화 감지 — 저장 불가 (다른 거리에서 재캡처 필요)"
            return {
                "ok": False, "degenerate": True,
                "error": ("광평면이 퇴화했습니다(" + ", ".join(health["reasons"]) + "). "
                          "체커보드를 여러 '거리'(가까이·멀리)와 위·아래 위치로 옮겨가며 다시 캡처하세요. "
                          f"현재 깊이 범위 {depth_span:.0f}mm — 200mm 이상 권장."),
                "health": health,
                "intrinsic_rms_px": round(float(rms), 4),
                "plane_rms_mm": round(fit["rms"], 4),
                "n_poses": len(self.poses), "per_pose": per_pose,
                "status": None,
            }

        self.model = LaserPlaneModel(
            n=fit["n"], d=fit["d"], K=K, dist=dist,
            meta={
                "camera_id": self.camera_id, "mode": "combined",
                "n_poses": len(self.poses), "n_points": fit["n_points"],
                "intrinsic_rms_px": round(float(rms), 4),
                "fit_rms_mm": round(fit["rms"], 4), "fit_max_mm": round(fit["max"], 4),
                "square_size_mm": self.square_mm,
                "pattern_inner_corners": [self.inner_cols, self.inner_rows],
                "image_size": {"width": self.image_size[0], "height": self.image_size[1]},
                "board_z_mm": zs, "depth_span_mm": depth_span,
                "plane_health": health, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        warn = "  ⚠ 깊이 다양성이 낮음 — 더 다양한 거리 권장" if health["weak"] else ""
        self.last_message = (
            f"통합 피팅 완료 — 내부 RMS {rms:.3f}px · 광평면 RMS {fit['rms']:.3f}mm ({len(self.poses)}자세){warn}"
        )
        return {"ok": True, "intrinsic_rms_px": round(float(rms), 4),
                "plane_rms_mm": round(fit["rms"], 4), "plane_max_mm": round(fit["max"], 4),
                "n_poses": len(self.poses), "n_points": fit["n_points"],
                "depth_span_mm": depth_span, "health": health, "weak": health["weak"],
                "per_pose": per_pose}

    def measure_points(self, uv_a, uv_b) -> dict:
        if self.model is None:
            return {"ok": False, "error": "아직 피팅되지 않았습니다"}
        return LaserPlaneSession.measure_points(self, uv_a, uv_b)  # 동일 로직 재사용

    def reset(self):
        self.pending_corners = None
        self.poses.clear()
        self.K = self.dist = self.model = self.plane_fit = self.intrinsic_rms = None
        self.last_message = "세션 초기화됨"

    def status(self) -> dict:
        return {
            "camera_id": self.camera_id, "mode": "combined",
            "pattern_inner_corners": [self.inner_cols, self.inner_rows],
            "square_size_mm": self.square_mm,
            "image_size": {"width": self.image_size[0], "height": self.image_size[1]},
            "n_poses": len(self.poses),
            "pending_off": self.pending_corners is not None,
            "fitted": self.model is not None,
            "intrinsic_rms_px": None if self.intrinsic_rms is None else round(self.intrinsic_rms, 4),
            "plane_rms_mm": None if self.plane_fit is None else round(self.plane_fit["rms"], 4),
            "message": self.last_message,
        }


# ─────────────────────────────────────────────────────────────
# 합성 자체검증 (실데이터·카메라 없이 수학 정확성 증명)
# ─────────────────────────────────────────────────────────────
def _plane_intersection_line(p1: Plane, p2: Plane) -> Tuple[np.ndarray, np.ndarray]:
    """두 평면의 교선: (점 p0, 방향 dir)."""
    n1, d1 = p1
    n2, d2 = p2
    n1 = np.asarray(n1, float); n2 = np.asarray(n2, float)
    direction = np.cross(n1, n2)
    direction = direction / np.linalg.norm(direction)
    # n1·X=-d1, n2·X=-d2, dir·X=0 을 만족하는 한 점
    A = np.stack([n1, n2, direction])
    b = np.array([-d1, -d2, 0.0])
    p0 = np.linalg.solve(A, b)
    return p0, direction


def _self_test(verbose: bool = True) -> dict:
    rng = np.random.default_rng(7)

    # 실제 캘리브에서 나온 값과 유사한 카메라 (6048x8064)
    W, H = 6048, 8064
    K = np.array([[5731.0, 0, 3024.0], [0, 5637.0, 4032.0], [0, 0, 1.0]], np.float64)
    dist = np.array([0.14, -0.09, 0.004, 0.006, -1.46], np.float64)  # 실측 유사
    square_mm = 20.0
    cols, rows = 12, 8

    # 정답 레이저 광평면 (카메라 좌표계): 위→아래로 비스듬한 평면
    n_gt = np.array([0.15, 0.82, -0.55], np.float64)
    n_gt /= np.linalg.norm(n_gt)
    d_gt = -n_gt @ np.array([0.0, 0.0, 500.0])  # 광축상 500mm 부근 통과
    plane_gt = (n_gt, float(d_gt))

    objp = make_object_points(cols, rows, square_mm)

    # 여러 자세의 보드 (거리 400~650mm, 다양한 기울기)
    depths = [420, 470, 520, 570, 620]
    tilts = [(-12, 8), (6, -10), (15, 5), (-8, -14), (10, 12)]

    all_pts_3d: List[np.ndarray] = []
    per_pose = []
    session = LaserPlaneSession(0, cols, rows, square_mm, K, dist)
    for (Z, (rx_deg, ry_deg)) in zip(depths, tilts):
        rx, ry = np.radians(rx_deg), np.radians(ry_deg)
        Rx = cv2.Rodrigues(np.array([rx, 0, 0]))[0]
        Ry = cv2.Rodrigues(np.array([0, ry, 0]))[0]
        R = Ry @ Rx
        # 보드 중심이 광축 근처 Z에 오도록 t 설정
        center = R @ np.array([(cols - 1) * square_mm / 2, (rows - 1) * square_mm / 2, 0.0])
        t = np.array([rng.uniform(-40, 40), rng.uniform(-40, 40), float(Z)]) - center
        rvec = cv2.Rodrigues(R)[0]
        tvec = t.reshape(3, 1)

        # 코너 픽셀 생성(왜곡 포함) — 자세 복원용
        corners, _ = cv2.projectPoints(objp, rvec, tvec, K, dist)
        corners = corners.reshape(-1, 2) + rng.normal(0, 0.1, (len(objp), 2))  # 0.1px 잡음

        board_plane_true = plane_from_board_pose(rvec, tvec)

        # 보드 위의 레이저 = 광평면 ∩ 보드평면 (3D 선). 보드 안쪽 구간만 샘플.
        p0, ddir = _plane_intersection_line(plane_gt, board_plane_true)
        Rt = R.T
        laser_uv = []
        for s in np.linspace(-400, 400, 240):
            Xc = p0 + s * ddir                       # 카메라 좌표계 3D
            Xb = Rt @ (Xc - t)                       # 보드 좌표계
            if -square_mm <= Xb[0] <= cols * square_mm and -square_mm <= Xb[1] <= rows * square_mm:
                uv, _ = cv2.projectPoints(Xc.reshape(1, 3), np.zeros(3), np.zeros(3), K, dist)
                px = uv.reshape(2) + rng.normal(0, 0.2, 2)  # 0.2px 잡음
                if 0 <= px[0] < W and 0 <= px[1] < H:
                    laser_uv.append(px)
        laser_uv = np.array(laser_uv)

        # ── 파이프라인: 코너→보드자세→보드평면, 레이저픽셀→광선∩보드평면→3D ──
        pose = solve_board_pose(objp, corners, K, dist)
        board_plane_est = plane_from_board_pose(*pose)
        pts3d = board_points_to_3d(laser_uv, board_plane_est, K, dist)
        all_pts_3d.append(pts3d)
        per_pose.append((Z, len(laser_uv)))
        session.add_pose(corners, laser_uv)  # 세션 경로도 함께 검증

    pts = np.vstack(all_pts_3d)
    fit = fit_plane_svd(pts)

    # 정답과 비교 (법선은 부호 무관)
    n_est = fit["n"]
    if n_est @ n_gt < 0:
        n_est = -n_est
        d_est = -fit["d"]
    else:
        d_est = fit["d"]
    angle_deg = float(np.degrees(np.arccos(np.clip(n_est @ n_gt, -1, 1))))
    # 정답 평면 위 점들이 추정 평면에서 얼마나 떨어지나 (정규화: 광축 500mm 지점)
    d_norm_diff = abs(d_est - d_gt)

    # 복원 정확도: 정답 광평면 위 임의 3D → 픽셀 → 모델 복원 → 오차(mm)
    model = LaserPlaneModel(n=n_est, d=d_est, K=K, dist=dist)
    test_line = _plane_intersection_line(plane_gt, (np.array([0, 0, 1.0]), -500.0))
    p0t, dt = test_line
    errs = []
    for s in np.linspace(-150, 150, 40):
        Xt = p0t + s * dt
        uv, _ = cv2.projectPoints(Xt.reshape(1, 3), np.zeros(3), np.zeros(3), K, dist)
        Xr = model.reconstruct(uv.reshape(1, 2))[0]
        errs.append(np.linalg.norm(Xr - Xt))
    recon_mm = float(np.mean(errs))

    result = {
        "poses": per_pose,
        "n_points": fit["n_points"],
        "plane_fit_rms_mm": round(fit["rms"], 4),
        "plane_fit_max_mm": round(fit["max"], 4),
        "normal_angle_err_deg": round(angle_deg, 4),
        "offset_err_mm": round(d_norm_diff, 4),
        "reconstruct_err_mm": round(recon_mm, 4),
    }
    if verbose:
        print("=" * 64)
        print("레이저 광평면 캘리브레이션 — 합성 자체검증")
        print("=" * 64)
        print("자세(거리Z, 레이저점수):", per_pose)
        print("피팅 점 수           :", fit["n_points"])
        print("평면 피팅 RMS        : %.4f mm" % fit["rms"])
        print("평면 피팅 최대오차   : %.4f mm" % fit["max"])
        print("법선 각도 오차       : %.4f deg" % angle_deg)
        print("오프셋(거리) 오차    : %.4f mm" % d_norm_diff)
        print("3D 복원 오차(평균)   : %.4f mm" % recon_mm)
        ok = angle_deg < 0.2 and recon_mm < 0.5
        print("-" * 64)
        print("판정:", "PASS ✅ (기하 파이프라인 정확)" if ok else "FAIL ❌ 확인 필요")

    # ── 세션(add_pose→fit→measure) 경로 검증 ──
    sfit = session.fit()
    # 정답 광평면 위 두 점을 픽셀로 → 세션 측정 → 실제 거리와 비교
    p0m, dm = _plane_intersection_line(plane_gt, (np.array([0, 0, 1.0]), -500.0))
    A3, B3 = p0m + (-60) * dm, p0m + 60 * dm
    uvA = cv2.projectPoints(A3.reshape(1, 3), np.zeros(3), np.zeros(3), K, dist)[0].reshape(2)
    uvB = cv2.projectPoints(B3.reshape(1, 3), np.zeros(3), np.zeros(3), K, dist)[0].reshape(2)
    meas = session.measure_points(uvA, uvB)
    true_dist = float(np.linalg.norm(B3 - A3))
    if verbose:
        print("=" * 64)
        print("세션 경로 검증 (add_pose → fit → measure_points)")
        print("  세션 피팅 RMS       : %.4f mm (%d자세, %d점)"
              % (sfit["rms_mm"], sfit["n_poses"], sfit["n_points"]))
        print("  깊이 스프레드       : %.1f mm" % sfit["depth_span_mm"])
        print("  측정 거리(추정/실제): %.3f / %.3f mm  (오차 %.4f)"
              % (meas["distance_mm"], true_dist, abs(meas["distance_mm"] - true_dist)))
        sok = sfit["ok"] and abs(meas["distance_mm"] - true_dist) < 0.5
        print("  판정:", "PASS ✅" if sok else "FAIL ❌")
    result["session_fit_rms_mm"] = sfit["rms_mm"]
    result["session_measure_err_mm"] = round(abs(meas["distance_mm"] - true_dist), 4)
    return result


if __name__ == "__main__":
    _self_test()
