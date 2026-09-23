# -*- coding: utf-8 -*-
"""레이저 광평면(3D) 캘리브레이션 라우터 — 기존 measurement/calibration과 분리.

흐름:
  1) start   : 저장된 내부파라미터(calibration_data/*.json)로 세션 시작
  2) capture : 보드+레이저 프레임 1자세 → 코너·레이저 검출 → 보드 위 3D 적립
  3) fit     : 누적 3D 점 → 광평면 피팅(RMS)
  4) save    : laserplane_data/camera_X_laserplane.json 저장
  5) measure : 두 픽셀 → 3D 복원 → 실제 거리(mm)

기존 코드는 읽기만(재사용)한다: 내부파라미터 JSON, 코너검출(CalibrationSession),
레이저검출(laser_manager). 측정 파이프라인은 건드리지 않는다.
"""
import os
import sys

project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_path)

import base64
import glob
import json
import re
from datetime import datetime
from typing import List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils import laser_manager as lm
from utils import laser_plane_manager as lpm
from utils.calibration_manager import CalibrationConfig, CalibrationSession
from utils.camera_client import get_frame_bgr

router = APIRouter(prefix="/laserplane", tags=["laserplane"])

PLANE_DIR = os.path.join(os.path.dirname(__file__), "..", "laserplane_data")
FRAME_RETRY_COUNT = 25
FRAME_RETRY_DELAY_SEC = 0.08

# 카메라별 세션 (메모리) — 통합 캘리브레이션 세션 + 마지막 측정 프레임
_COMBINED: dict = {}
_MEAS: dict = {}  # 측정용: 카메라별 마지막 캡처의 레이저 점(u,v) + image_size


async def _fetch_bgr(camera_id: int):
    import asyncio
    for attempt in range(FRAME_RETRY_COUNT):
        img = await get_frame_bgr(camera_id)
        if img is not None:
            return img
        if attempt < FRAME_RETRY_COUNT - 1:
            await asyncio.sleep(FRAME_RETRY_DELAY_SEC)
    return None


def _plane_slug(name: Optional[str]) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", (name or "").strip())
    return s.strip("_")[:40]


def _new_plane_path(camera_id: int, name: Optional[str]) -> str:
    """이름 지정 저장 — 파일명에 슬러그 + 타임스탬프를 붙여 이력 보존."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _plane_slug(name)
    fname = f"camera_{camera_id}_laserplane_{slug + '_' if slug else ''}{ts}.json"
    return os.path.join(PLANE_DIR, fname)


def _list_planes(camera_id: int) -> List[str]:
    """해당 카메라의 저장된 광평면 파일들 (최신순)."""
    files = glob.glob(os.path.join(PLANE_DIR, f"camera_{camera_id}_laserplane*.json"))
    return sorted(files, key=os.path.getmtime, reverse=True)


def _resolve_plane_path(camera_id: int, plane_file: Optional[str]) -> Optional[str]:
    """plane_file 지정 시 그 파일, 없으면 최신 저장본."""
    if plane_file:
        p = os.path.join(PLANE_DIR, os.path.basename(plane_file))
        return p if os.path.exists(p) else None
    files = _list_planes(camera_id)
    return files[0] if files else None


def _capture_overlay(img, corners, all_laser_uv, onboard_uv, max_w: int = 900) -> Optional[str]:
    """검출 결과 오버레이(base64 JPEG): 코너 + 레이저(회색=제외, 초록=보드 위 사용)."""
    ov = img.copy()
    try:
        # 전체 레이저(회색) → 보드 밖은 제외됐음을 시각화
        for p in np.asarray(all_laser_uv, np.int32).reshape(-1, 2):
            cv2.circle(ov, (int(p[0]), int(p[1])), 2, (150, 150, 150), -1)
        # 보드 위 사용된 레이저(초록)
        if onboard_uv is not None:
            for p in np.asarray(onboard_uv, np.int32).reshape(-1, 2):
                cv2.circle(ov, (int(p[0]), int(p[1])), 3, (0, 255, 0), -1)
        # 체커보드 코너(빨강 원)
        if corners is not None:
            for p in np.asarray(corners, np.int32).reshape(-1, 2):
                cv2.circle(ov, (int(p[0]), int(p[1])), 4, (0, 0, 255), 2)
    except Exception:
        pass
    h, w = ov.shape[:2]
    if w > max_w:
        ov = cv2.resize(ov, (max_w, int(max_w * h / w)))
    ok, buf = cv2.imencode(".jpg", ov, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


# ─────────────────────────────────────────────────────────────
# 요청 모델
# ─────────────────────────────────────────────────────────────
class MeasureRequest(BaseModel):
    a_uv: List[float] = Field(..., min_length=2, max_length=2)
    b_uv: List[float] = Field(..., min_length=2, max_length=2)
    snap: bool = Field(True, description="클릭점을 가장 가까운 레이저 점으로 보정")
    plane_file: Optional[str] = Field(None, description="사용할 저장 광평면 파일 (없으면 최신)")


class MeasureCaptureRequest(BaseModel):
    laser_color: str = Field("auto", description="blue | red | auto")
    detector: str = Field("chroma")
    plane_file: Optional[str] = Field(None, description="사용할 저장 광평면 파일 (없으면 최신)")
    sensitivity: int = Field(50, ge=0, le=100, description="자동 엣지 민감도 0(엄격)~100(민감)")


class SaveRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=64, description="저장 이름(선택)")


class CombinedStartRequest(BaseModel):
    inner_cols: int = Field(12, ge=2, le=40)
    inner_rows: int = Field(8, ge=2, le=40)
    square_size_mm: float = Field(20.0, gt=0)


class CombinedOnRequest(BaseModel):
    laser_color: str = Field("auto", description="blue | red | auto")
    detector: str = Field("chroma")


# ─────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────
@router.get("/planes/{camera_id}")
async def list_planes(camera_id: int):
    """저장된 광평면 목록 (측정에서 선택)."""
    items = []
    for path in _list_planes(camera_id):
        try:
            with open(path, "r", encoding="utf-8") as f:
                j = json.load(f)
        except Exception:
            continue
        meta = j.get("meta", {}) if isinstance(j, dict) else {}
        items.append({
            "file": os.path.basename(path),
            "name": meta.get("name"),
            "created_at": meta.get("created_at"),
            "fit_rms_mm": meta.get("fit_rms_mm"),
            "intrinsic_rms_px": meta.get("intrinsic_rms_px"),
            "n_poses": meta.get("n_poses"),
            "image_size": meta.get("image_size"),
        })
    return {"planes": items}


@router.get("/model/{camera_id}")
async def get_model(camera_id: int, plane_file: Optional[str] = None):
    path = _resolve_plane_path(camera_id, plane_file)
    if not path:
        return JSONResponse(status_code=404, content={"error": "저장된 광평면이 없습니다."})
    model = lpm.LaserPlaneModel.load(path)
    return {"plane": {"n": [float(x) for x in model.n], "d": float(model.d)},
            "file": os.path.basename(path), "meta": model.meta}


def _load_measure_model(camera_id: int, plane_file: Optional[str] = None) -> Optional[lpm.LaserPlaneModel]:
    """측정용 모델: 지정 파일 → 최신 저장본 → (없으면) 방금 피팅한 세션 모델."""
    path = _resolve_plane_path(camera_id, plane_file)
    if path:
        return lpm.LaserPlaneModel.load(path)
    # 저장본이 없으면 방금 피팅한(미저장) 통합 세션 모델 사용
    sess = _get_combined(camera_id)
    if sess is not None and getattr(sess, "model", None) is not None:
        return sess.model
    return None


def _snap_to_laser(uv, points: np.ndarray, max_dist: float = 60.0):
    """클릭점을 가장 가까운 레이저 점으로 보정 (max_dist px 이내)."""
    if points is None or len(points) == 0:
        return uv, False
    p = np.asarray(uv, np.float64)
    d = np.linalg.norm(points - p, axis=1)
    i = int(np.argmin(d))
    if d[i] <= max_dist:
        return [float(points[i, 0]), float(points[i, 1])], True
    return uv, False


def _measure_overlay(img, laser_uv, edge, max_w: int = 2000) -> Optional[str]:
    """레이저(초록) + 자동 엣지 끝점(A 초록/B 빨강) + 연결선 오버레이."""
    ov = img.copy()
    try:
        for p in np.asarray(laser_uv, np.int32).reshape(-1, 2):
            cv2.circle(ov, (int(p[0]), int(p[1])), 2, (0, 220, 0), -1)
        if edge:
            la = (int(round(edge["left_end"]["x"])), int(round(edge["left_end"]["y"])))
            rb = (int(round(edge["right_end"]["x"])), int(round(edge["right_end"]["y"])))
            cv2.line(ov, la, rb, (0, 255, 255), 3, cv2.LINE_AA)
            cv2.circle(ov, la, 11, (0, 255, 0), 3)
            cv2.circle(ov, rb, 11, (0, 0, 255), 3)
    except Exception:
        pass
    h, w = ov.shape[:2]
    if w > max_w:
        ov = cv2.resize(ov, (max_w, int(max_w * h / w)))
    ok, buf = cv2.imencode(".jpg", ov, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _edge_thresholds(sensitivity: int):
    """민감도 0(엄격)~100(민감) → (min_hole, noise_mult, min_jump)."""
    s = max(0, min(100, int(sensitivity))) / 100.0
    min_hole = 3 if s >= 0.5 else 4
    noise_mult = 8.0 - 4.0 * s   # 8.0 → 4.0
    min_jump = 3.0 - 1.0 * s     # 3.0 → 2.0
    return min_hole, noise_mult, min_jump


def _measure_image(camera_id: int, img: np.ndarray, model, laser_color: str, detector: str,
                   size_warning: Optional[str] = None, sensitivity: int = 50) -> dict:
    """이미지 1장에 대해 레이저 검출 → 자동 엣지 → 3D 간격. 캡처/파일 공용."""
    fh, fw = img.shape[:2]
    color = str(laser_color or "auto").lower()
    if color == "auto":
        color = lm.detect_laser_color(img)
    profile, _mask = lm.detect_laser_profile_for_gap(img, laser_color=color, detector=detector)

    def _nvalid(p):
        return int(np.count_nonzero(~np.isnan(p))) if p is not None else 0

    # 색이 틀려 검출이 거의 0이면 반대 색으로 자동 재시도(더 많은 쪽 채택)
    if _nvalid(profile) < 100:
        alt = "red" if color == "blue" else "blue"
        p2, _m2 = lm.detect_laser_profile_for_gap(img, laser_color=alt, detector=detector)
        if _nvalid(p2) > _nvalid(profile):
            color, profile = alt, p2

    laser_uv = np.array(lm.profile_to_points(profile), np.float64) if profile is not None else np.zeros((0, 2))
    _MEAS[camera_id] = {"points": laser_uv, "image_size": (fw, fh)}

    auto, edge = None, None
    if profile is not None:
        mh, nm, mj = _edge_thresholds(sensitivity)
        edge, edge_err = lm.measure_edge_from_profile(
            profile, end_margin_px=lm.DEFAULT_EDGE_END_MARGIN_PX,
            min_hole=mh, noise_mult=nm, min_jump=mj,
        )
        if edge and not edge_err:
            lu = [float(edge["left_end"]["x"]), float(edge["left_end"]["y"])]
            ru = [float(edge["right_end"]["x"]), float(edge["right_end"]["y"])]
            A = model.reconstruct(np.asarray(lu, np.float64).reshape(1, 2))[0]
            B = model.reconstruct(np.asarray(ru, np.float64).reshape(1, 2))[0]
            if np.isfinite(A).all() and np.isfinite(B).all():
                delta = B - A
                auto = {
                    "a_uv": [round(lu[0], 1), round(lu[1], 1)], "b_uv": [round(ru[0], 1), round(ru[1], 1)],
                    "distance_mm": round(float(np.linalg.norm(delta)), 4),
                    "depth_diff_mm": round(abs(float(delta[2])), 4),
                    "point_a_mm": [round(float(x), 3) for x in A],
                    "point_b_mm": [round(float(x), 3) for x in B],
                    "kind": edge.get("kind"), "gap_px": edge.get("gap_px"), "snr": edge.get("snr"),
                }
    overlay = _measure_overlay(img, laser_uv, edge if auto else None)
    out = {"image": overlay, "laser_color": color, "n_laser": int(len(laser_uv)),
           "image_size": {"width": fw, "height": fh}, "auto": auto}
    if size_warning:
        out["warning"] = size_warning
    return out


def _model_size_warning(model, fw: int, fh: int) -> Optional[str]:
    """업로드/캡처 이미지 해상도가 캘리브 해상도와 다르면 경고(3D 부정확)."""
    sz = (model.meta or {}).get("image_size") if isinstance(model.meta, dict) else None
    if isinstance(sz, dict) and sz.get("width") and sz.get("height"):
        if int(sz["width"]) != fw or int(sz["height"]) != fh:
            return (f"이미지 해상도({fw}×{fh})가 캘리브레이션({sz['width']}×{sz['height']})과 "
                    "다릅니다 — 3D 값이 부정확할 수 있습니다. 같은 카메라·해상도로 촬영하세요.")
    return None


@router.post("/measure_capture/{camera_id}")
async def measure_capture(camera_id: int, req: MeasureCaptureRequest = MeasureCaptureRequest()):
    """카메라에서 1장 캡처 → 레이저 검출 → 자동 엣지(간격) + 3D 복원."""
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})
    model = _load_measure_model(camera_id, req.plane_file)
    if model is None:
        return JSONResponse(status_code=409, content={"error": "광평면이 없습니다. 먼저 캘리브레이션(피팅/저장)하세요."})
    img = await _fetch_bgr(camera_id)
    if img is None:
        return JSONResponse(status_code=503, content={"error": "프레임을 가져올 수 없습니다 (카메라 상태 확인)"})
    warn = _model_size_warning(model, img.shape[1], img.shape[0])
    return _measure_image(camera_id, img, model, req.laser_color, req.detector, warn, req.sensitivity)


@router.post("/measure_file/{camera_id}")
async def measure_file(
    camera_id: int,
    file: UploadFile = File(...),
    laser_color: str = Form("auto"),
    detector: str = Form("chroma"),
    plane_file: Optional[str] = Form(None),
    sensitivity: int = Form(50),
):
    """PC에서 올린 이미지로 측정 → 레이저 검출 → 자동 엣지(간격) + 3D 복원.

    ⚠️ 이미지는 캘리브레이션과 동일 카메라·해상도여야 3D가 정확하다.
    """
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})
    model = _load_measure_model(camera_id, plane_file)
    if model is None:
        return JSONResponse(status_code=409, content={"error": "광평면이 없습니다. 먼저 캘리브레이션(피팅/저장)하세요."})
    try:
        raw = await file.read()
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        img = None
    if img is None:
        return JSONResponse(status_code=400, content={"error": "이미지를 읽을 수 없습니다 (jpg/png 확인)"})
    warn = _model_size_warning(model, img.shape[1], img.shape[0])
    return _measure_image(camera_id, img, model, laser_color, detector, warn, sensitivity)


@router.post("/measure/{camera_id}")
async def measure(camera_id: int, req: MeasureRequest):
    model = _load_measure_model(camera_id, req.plane_file)
    if model is None:
        return JSONResponse(status_code=409, content={"error": "광평면이 없습니다. 캘리브레이션(피팅/저장) 후 측정하세요."})

    a_uv, b_uv = list(req.a_uv), list(req.b_uv)
    snapped = False
    meas = _MEAS.get(camera_id)
    if req.snap and meas is not None:
        pts = meas.get("points")
        a_uv, sa = _snap_to_laser(a_uv, pts)
        b_uv, sb = _snap_to_laser(b_uv, pts)
        snapped = sa or sb

    A = model.reconstruct(np.asarray(a_uv, np.float64).reshape(1, 2))[0]
    B = model.reconstruct(np.asarray(b_uv, np.float64).reshape(1, 2))[0]
    if not (np.isfinite(A).all() and np.isfinite(B).all()):
        return JSONResponse(status_code=422, content={"error": "3D 복원 실패(광선이 평면과 평행)"})
    delta = B - A
    return {
        "ok": True,
        "a_uv": [round(x, 1) for x in a_uv], "b_uv": [round(x, 1) for x in b_uv],
        "snapped": snapped,
        "point_a_mm": [round(float(x), 3) for x in A],
        "point_b_mm": [round(float(x), 3) for x in B],
        "distance_mm": round(float(np.linalg.norm(delta)), 4),
        "delta_mm": {"x": round(float(delta[0]), 4), "y": round(float(delta[1]), 4), "z": round(float(delta[2]), 4)},
        "depth_diff_mm": round(abs(float(delta[2])), 4),
    }


# ─────────────────────────────────────────────────────────────
# 통합 캘리브레이션 (내부파라미터 + 광평면 한 번에, OFF/ON)
# ─────────────────────────────────────────────────────────────
def _get_combined(camera_id: int) -> Optional[lpm.LaserPlaneCombinedSession]:
    return _COMBINED.get(camera_id)


async def _detect_corners(camera_id, session):
    img = await _fetch_bgr(camera_id)
    if img is None:
        return None, None, JSONResponse(status_code=503, content={"error": "프레임을 가져올 수 없습니다 (카메라 상태 확인)"})
    board = CalibrationSession(camera_id=camera_id, config=CalibrationConfig(
        inner_cols=session.inner_cols, inner_rows=session.inner_rows, square_size_mm=session.square_mm))
    found, corners = board.detect_corners_for_capture(img)
    if not found or corners is None:
        return img, None, JSONResponse(status_code=422, content={
            "error": f"체커보드 검출 실패 (내부코너 {session.inner_cols}×{session.inner_rows})",
            "overlay": _capture_overlay(img, None, np.zeros((0, 2)), None), "status": session.status()})
    return img, corners.reshape(-1, 2), None


@router.post("/combined/start/{camera_id}")
async def combined_start(camera_id: int, req: CombinedStartRequest = CombinedStartRequest()):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})
    img = await _fetch_bgr(camera_id)
    if img is None:
        return JSONResponse(status_code=503, content={"error": "프레임을 가져올 수 없습니다 (카메라를 먼저 시작하세요)"})
    fh, fw = img.shape[:2]
    session = lpm.LaserPlaneCombinedSession(camera_id, req.inner_cols, req.inner_rows, req.square_size_mm, (fw, fh))
    _COMBINED[camera_id] = session
    return {"message": "통합 캘리브레이션 세션 시작", "image_size": {"width": fw, "height": fh}, "status": session.status()}


@router.get("/combined/status/{camera_id}")
async def combined_status(camera_id: int):
    session = _get_combined(camera_id)
    n_saved = len(_list_planes(camera_id))
    if session is None:
        return {"started": False, "saved_model": n_saved > 0, "saved_count": n_saved}
    return {"started": True, "saved_model": n_saved > 0, "saved_count": n_saved, "status": session.status()}


@router.post("/combined/capture_off/{camera_id}")
async def combined_capture_off(camera_id: int):
    session = _get_combined(camera_id)
    if session is None:
        return JSONResponse(status_code=409, content={"error": "세션이 없습니다. 먼저 시작하세요."})
    img, corners, err = await _detect_corners(camera_id, session)
    if err is not None:
        return err
    res = session.add_off(corners)
    overlay = _capture_overlay(img, corners, np.zeros((0, 2)), None)
    if not res.get("ok"):
        return JSONResponse(status_code=422, content={**res, "overlay": overlay, "status": session.status()})
    return {**res, "overlay": overlay, "status": session.status()}


@router.post("/combined/capture_on/{camera_id}")
async def combined_capture_on(camera_id: int, req: CombinedOnRequest = CombinedOnRequest()):
    session = _get_combined(camera_id)
    if session is None:
        return JSONResponse(status_code=409, content={"error": "세션이 없습니다. 먼저 시작하세요."})
    img = await _fetch_bgr(camera_id)
    if img is None:
        return JSONResponse(status_code=503, content={"error": "프레임을 가져올 수 없습니다"})
    color = str(req.laser_color or "auto").lower()
    if color == "auto":
        color = lm.detect_laser_color(img)
    profile, _mask = lm.detect_laser_profile_for_gap(img, laser_color=color, detector=req.detector)
    laser_uv = np.array(lm.profile_to_points(profile), np.float64) if profile is not None else np.zeros((0, 2))
    res = session.add_on(laser_uv)
    overlay = _capture_overlay(img, session.pending_corners, laser_uv, session.last_onboard_uv)
    if not res.get("ok"):
        return JSONResponse(status_code=422, content={**res, "laser_color": color, "overlay": overlay, "status": session.status()})
    return {**res, "laser_color": color, "overlay": overlay, "status": session.status()}


@router.post("/combined/capture_single/{camera_id}")
async def combined_capture_single(camera_id: int, req: CombinedOnRequest = CombinedOnRequest()):
    """단일 프레임 — 레이저 켠 채로 한 장에서 코너 + 레이저를 동시에 검출해 1자세 확정."""
    session = _get_combined(camera_id)
    if session is None:
        return JSONResponse(status_code=409, content={"error": "세션이 없습니다. 먼저 시작하세요."})
    img, corners, err = await _detect_corners(camera_id, session)
    if err is not None:
        return err
    color = str(req.laser_color or "auto").lower()
    if color == "auto":
        color = lm.detect_laser_color(img)
    profile, _mask = lm.detect_laser_profile_for_gap(img, laser_color=color, detector=req.detector)
    laser_uv = np.array(lm.profile_to_points(profile), np.float64) if profile is not None else np.zeros((0, 2))
    # 한 프레임의 코너+레이저로 1자세 확정 (내부적으로 off→on)
    session.add_off(corners)
    res = session.add_on(laser_uv)
    overlay = _capture_overlay(img, corners, laser_uv, session.last_onboard_uv)
    if not res.get("ok"):
        session.pending_corners = None  # 실패 시 대기 코너 정리
        return JSONResponse(status_code=422, content={**res, "laser_color": color, "overlay": overlay, "status": session.status()})
    return {**res, "laser_color": color, "overlay": overlay, "status": session.status()}


@router.post("/combined/fit/{camera_id}")
async def combined_fit(camera_id: int):
    session = _get_combined(camera_id)
    if session is None:
        return JSONResponse(status_code=409, content={"error": "세션이 없습니다."})
    res = session.fit()
    if not res.get("ok"):
        return JSONResponse(status_code=422, content={**res, "status": session.status()})
    return {**res, "status": session.status()}


@router.post("/combined/save/{camera_id}")
async def combined_save(camera_id: int, req: SaveRequest = SaveRequest()):
    session = _get_combined(camera_id)
    if session is None or session.model is None:
        return JSONResponse(status_code=409, content={"error": "저장할 결과가 없습니다. 먼저 피팅하세요."})
    name = (req.name or "").strip() or None
    session.model.meta["name"] = name
    path = session.model.save(_new_plane_path(camera_id, name))
    return {"saved": True, "path": os.path.basename(path), "name": name, "meta": session.model.meta}


@router.post("/combined/reset/{camera_id}")
async def combined_reset(camera_id: int):
    session = _get_combined(camera_id)
    if session is None:
        return JSONResponse(status_code=409, content={"error": "세션이 없습니다."})
    session.reset()
    return {"message": "초기화됨", "status": session.status()}
