import os
import sys

project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_path)

import asyncio

import cv2
import numpy as np
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from utils.camera_grab_v2 import get_frame
from utils.calibration_manager import (
    CAPTURE_MAX_EDGE_PX,
    CalibrationConfig,
    MIN_SAMPLES,
    calibration_manager,
)

router = APIRouter(prefix="/calibration", tags=["calibration"])

CALIB_SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "calibration_data")


class CalibrationConfigRequest(BaseModel):
    inner_cols: int = Field(3, ge=2, le=20, description="체커보드 내부 코너 열 수")
    inner_rows: int = Field(3, ge=2, le=20, description="체커보드 내부 코너 행 수")
    square_size_mm: float = Field(20.0, gt=0, description="한 칸(정사각형) 변 길이 (mm)")


CAPTURE_RETRY_COUNT = 10
CAPTURE_RETRY_DELAY_SEC = 0.08
FRAME_RETRY_COUNT = 25
FRAME_RETRY_DELAY_SEC = 0.08
# 프리뷰는 속도(부드러운 갱신)가 안정감에 더 중요 — 캡처는 원본 해상도 사용
PREVIEW_STREAM_WIDTH = 1280
PREVIEW_STREAM_HEIGHT = 720


def _cap_max_edge(image_bgr: np.ndarray, max_edge: int) -> np.ndarray:
    """캡처용 — 업스케일 없이 긴 변만 상한으로 축소 (코너 정밀도 유지)."""
    h, w = image_bgr.shape[:2]
    longest = max(w, h)
    if longest <= max_edge:
        return image_bgr
    scale = max_edge / longest
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)


async def _fetch_bgr(camera_id: int, use_full_resolution: bool = False):
    """그래빙 버퍼가 비어 있을 수 있어 짧게 재시도합니다."""
    for attempt in range(FRAME_RETRY_COUNT):
        if use_full_resolution:
            jpeg = await get_frame(camera_id, None, None)
        else:
            jpeg = await get_frame(
                camera_id, PREVIEW_STREAM_WIDTH, PREVIEW_STREAM_HEIGHT
            )

        if jpeg:
            arr = np.frombuffer(jpeg, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                if use_full_resolution:
                    return _cap_max_edge(img, CAPTURE_MAX_EDGE_PX)
                return img

        if attempt < FRAME_RETRY_COUNT - 1:
            await asyncio.sleep(FRAME_RETRY_DELAY_SEC)

    return None


def _session_status(session) -> dict:
    return {
        "camera_id": session.camera_id,
        "ui_camera_id": session.camera_id + 1,
        "active": session.active,
        "detected": session.last_detected,
        "sample_count": session.sample_count,
        "min_samples": MIN_SAMPLES,
        "message": session.last_message,
        "pattern": {
            "inner_cols": session.config.inner_cols,
            "inner_rows": session.config.inner_rows,
            "square_size_mm": session.config.square_size_mm,
        },
        "calibrated": session.camera_matrix is not None,
        "rms_error": session.rms_error,
        "per_view_errors": session.per_view_errors,
        "image_size": (
            {"width": session.image_size[0], "height": session.image_size[1]}
            if session.image_size
            else None
        ),
    }


@router.get("/status/{camera_id}")
async def calibration_status(camera_id: int):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})
    session = calibration_manager.get_session(camera_id)
    return {"status": _session_status(session)}


@router.post("/start/{camera_id}")
async def start_calibration(camera_id: int, config: CalibrationConfigRequest = CalibrationConfigRequest()):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})
    cfg = CalibrationConfig(
        inner_cols=config.inner_cols,
        inner_rows=config.inner_rows,
        square_size_mm=config.square_size_mm,
    )
    session = calibration_manager.start(camera_id, cfg)
    return {"message": "Calibration session started", "status": _session_status(session)}


@router.post("/stop/{camera_id}")
async def stop_calibration(camera_id: int):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})
    session = calibration_manager.stop(camera_id)
    return {"message": "Calibration session stopped", "status": _session_status(session)}


@router.get("/preview/{camera_id}")
async def calibration_preview(camera_id: int):
    """실시간 체커보드 검출 오버레이 JPEG (모니터링 화면용)"""
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    session = calibration_manager.get_session(camera_id)
    image_bgr = await _fetch_bgr(camera_id, use_full_resolution=False)
    if image_bgr is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "No frame available (camera not grabbing or buffer empty — check Monitor & camera status)",
            },
        )

    annotated, _info = session.preview_overlay(image_bgr)
    ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        return JSONResponse(status_code=500, content={"error": "Failed to encode preview"})

    return Response(content=buf.tobytes(), media_type="image/jpeg")


@router.post("/capture/{camera_id}")
async def capture_sample(camera_id: int):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    session = calibration_manager.get_session(camera_id)
    if not session.active:
        return JSONResponse(status_code=400, content={"error": "Calibration session is not active"})

    # 샘플 캡처는 프리뷰와 동일한 스트림 해상도(1280×720) — 검출이 빠르고 안정적.
    # (원본 해상도는 SaveImageToFileEx 변환이 수초~수십초 걸려 타임아웃 유발)
    result = None
    corner_count = session.config.inner_cols * session.config.inner_rows
    retry_count = max(CAPTURE_RETRY_COUNT, 10 + corner_count // 2)
    for attempt in range(retry_count):
        image_bgr = await _fetch_bgr(camera_id, use_full_resolution=False)
        if image_bgr is None:
            if attempt < retry_count - 1:
                await asyncio.sleep(CAPTURE_RETRY_DELAY_SEC)
                continue
            return JSONResponse(
                status_code=503,
                content={
                    "error": "No frame available (camera not grabbing or buffer empty — check Monitor & camera status)",
                },
            )

        result = session.add_sample(image_bgr)
        if result.get("success"):
            break
        if attempt < retry_count - 1:
            await asyncio.sleep(CAPTURE_RETRY_DELAY_SEC)

    status_code = 200 if result.get("success") else 400
    return JSONResponse(status_code=status_code, content={**result, "status": _session_status(session)})


@router.post("/run/{camera_id}")
async def run_calibration(camera_id: int):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    session = calibration_manager.get_session(camera_id)
    result = session.run_calibration()
    status_code = 200 if result.get("success") else 400
    return JSONResponse(status_code=status_code, content={**result, "status": _session_status(session)})


@router.post("/save/{camera_id}")
async def save_calibration(camera_id: int):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    session = calibration_manager.get_session(camera_id)
    try:
        path = session.save(CALIB_SAVE_DIR)
        return {"success": True, "message": "캘리브레이션 결과 저장됨", "path": path}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.post("/reset/{camera_id}")
async def reset_samples(camera_id: int):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})
    session = calibration_manager.get_session(camera_id)
    session.reset_samples()
    session.last_message = "샘플 초기화됨"
    return {"message": "Samples reset", "status": _session_status(session)}
