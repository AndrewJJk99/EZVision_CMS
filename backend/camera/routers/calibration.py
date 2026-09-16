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

from utils.camera_grab_v2 import (
    get_frame_bgr,
    letterbox_bgr,
    STREAM_DISPLAY_WIDTH,
    STREAM_DISPLAY_HEIGHT,
)
from utils.calibration_manager import (
    CalibrationConfig,
    MIN_SAMPLES,
    RECOMMENDED_SAMPLES,
    calibration_manager,
)

router = APIRouter(prefix="/calibration", tags=["calibration"])

CALIB_SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "calibration_data")


class AutoModeRequest(BaseModel):
    enabled: bool = Field(True, description="자동 수집 모드 on/off")


class CalibrationConfigRequest(BaseModel):
    inner_cols: int = Field(3, ge=2, le=20, description="체커보드 내부 코너 열 수")
    inner_rows: int = Field(3, ge=2, le=20, description="체커보드 내부 코너 행 수")
    square_size_mm: float = Field(20.0, gt=0, description="한 칸(정사각형) 변 길이 (mm)")
    distortion_model: str = Field("brown5", description="brown5 | rational")
    fix_aspect_ratio: bool = Field(True, description="fx≈fy 고정 (CALIB_FIX_ASPECT_RATIO)")


CAPTURE_RETRY_COUNT = 2
CAPTURE_RETRY_DELAY_SEC = 0.12
CAPTURE_DETECT_TIMEOUT_SEC = 20.0
FRAME_RETRY_COUNT = 30
FRAME_RETRY_DELAY_SEC = 0.12

# 카메라 BGR 접근 직렬화 (프리뷰 폭주 시 캡처·그래빙 경합 완화)
_bgr_locks: dict[int, asyncio.Lock] = {i: asyncio.Lock() for i in range(4)}


async def _fetch_bgr(camera_id: int, retry_count: int = FRAME_RETRY_COUNT):
    """카메라 원본 해상도 BGR (샘플 캡처·솔브용)."""
    lock = _bgr_locks[camera_id]
    async with lock:
        for attempt in range(max(1, int(retry_count))):
            img = await get_frame_bgr(camera_id)
            if img is not None:
                return img
            if attempt < retry_count - 1:
                await asyncio.sleep(FRAME_RETRY_DELAY_SEC)
    return None


async def _fetch_bgr_preview(camera_id: int):
    """프리뷰용 — 원본 1회 취득 후 1280×720 표시 해상도로 축소."""
    lock = _bgr_locks[camera_id]
    if lock.locked():
        return None
    async with lock:
        img = await get_frame_bgr(camera_id)
        if img is None:
            return None
        return letterbox_bgr(img, STREAM_DISPLAY_WIDTH, STREAM_DISPLAY_HEIGHT)


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
            "distortion_model": session.config.distortion_model,
            "fix_aspect_ratio": session.config.fix_aspect_ratio,
        },
        "calibrated": session.camera_matrix is not None,
        "rms_error": session.rms_error,
        "per_view_errors": session.per_view_errors,
        "excluded_sample_indices": session.excluded_sample_indices,
        "quality_report": session.quality_report,
        "quality_guide": session.quality_guide(),
        "recommended_samples": RECOMMENDED_SAMPLES,
        "distortion_model": session.config.distortion_model,
        "calib_flags": session.calib_flags,
        "auto": session.auto_state(),
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
        distortion_model=config.distortion_model,
        fix_aspect_ratio=config.fix_aspect_ratio,
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
    """체커보드 검출 오버레이 JPEG (표시용 1280×720, 샘플은 원본 캡처)."""
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    session = calibration_manager.get_session(camera_id)
    image_bgr = await _fetch_bgr_preview(camera_id)
    if image_bgr is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "No frame available (camera busy or buffer empty — check Monitor & camera status)",
            },
        )

    annotated, _info = session.preview_overlay(image_bgr)
    ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
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

    result = None
    last_error = None
    retry_count = CAPTURE_RETRY_COUNT
    for attempt in range(retry_count):
        image_bgr = await _fetch_bgr(camera_id, retry_count=2)
        if image_bgr is None:
            last_error = "프레임 없음"
            if attempt < retry_count - 1:
                await asyncio.sleep(CAPTURE_RETRY_DELAY_SEC)
                continue
            return JSONResponse(
                status_code=503,
                content={
                    "error": "No frame available (camera not grabbing or buffer empty — check Monitor & camera status)",
                },
            )

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(session.add_sample, image_bgr),
                timeout=CAPTURE_DETECT_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={
                    "success": False,
                    "message": "샘플 캡처 실패: 원본 이미지 체커보드 검출 시간이 너무 깁니다",
                    "status": _session_status(session),
                },
            )
        if result.get("success"):
            break
        last_error = result.get("message") or result.get("error")
        if attempt < retry_count - 1:
            await asyncio.sleep(CAPTURE_RETRY_DELAY_SEC)

    status_code = 200 if result.get("success") else 400
    return JSONResponse(
        status_code=status_code,
        content={
            **result,
            "message": result.get("message") or last_error or "샘플 캡처 실패",
            "status": _session_status(session),
        },
    )


@router.post("/auto/{camera_id}")
async def set_auto_mode(camera_id: int, req: AutoModeRequest = AutoModeRequest()):
    """자동 수집 모드 on/off."""
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    session = calibration_manager.get_session(camera_id)
    if req.enabled and not session.active:
        return JSONResponse(status_code=400, content={"error": "Calibration session is not active"})

    session.auto_enabled = bool(req.enabled)
    session.auto_reset()
    session.last_message = (
        "자동 모드 시작 — 보드를 여러 위치로 옮기고 잠깐씩 멈추세요"
        if req.enabled
        else "자동 모드 해제"
    )
    return {"message": session.last_message, "status": _session_status(session)}


@router.post("/auto/tick/{camera_id}")
async def auto_tick(camera_id: int):
    """자동 수집 루프 1스텝 (프론트가 주기 호출).

    판정은 축소 프리뷰로, 실제 샘플은 원본을 다시 grab해 담는다
    (해상도·정확도는 수동 캡처와 동일).
    """
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    session = calibration_manager.get_session(camera_id)
    if not session.active or not session.auto_enabled or session.auto_done:
        return {
            "idle": True,
            "accepted": False,
            "status": _session_status(session),
        }

    preview = await _fetch_bgr_preview(camera_id)
    if preview is None:
        # 카메라 락 경합/버퍼 비었을 때는 조용히 건너뛴다 (다음 틱에 재시도)
        return {"skipped": True, "accepted": False, "status": _session_status(session)}

    decision = await asyncio.to_thread(session.auto_evaluate, preview)

    accepted = False
    sample_message = None
    if decision.get("accept"):
        full = await _fetch_bgr(camera_id, retry_count=2)
        if full is not None:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(session.add_sample, full),
                    timeout=CAPTURE_DETECT_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                result = {"success": False, "message": "원본 검출 시간 초과"}
            accepted = bool(result.get("success"))
            sample_message = result.get("message")
            # 성공/실패 모두 쿨다운 — 같은 프레임을 연속 재시도하지 않도록
            session.mark_auto_accepted()

    # 샘플이 들어올 때마다 증분 재계산 → σ(불확실성) 갱신 후 수렴 판정
    if accepted and session.sample_count >= MIN_SAMPLES:
        await asyncio.to_thread(session.run_calibration)
        session.check_converged()

    # 종료 조건 충족 → 최종 결과 확정 (+ 품질 Pass면 자동 저장)
    finished = None
    saved_path = None
    if session.auto_ready():
        if session.last_calib_at_count == session.sample_count and session.camera_matrix is not None:
            # 방금 증분 재계산한 결과가 최신 — 중복 solve 생략
            calib = {
                "success": True,
                "message": "캘리브레이션 완료",
                "rms_error": session.rms_error,
                "per_view_errors": session.per_view_errors,
                "all_per_view_errors": session.per_view_errors,
                "excluded_sample_indices": session.excluded_sample_indices,
                "camera_matrix": session.camera_matrix.tolist(),
                "dist_coeffs": session.dist_coeffs.reshape(-1).tolist(),
                "focal_length_px": {
                    "fx": float(session.camera_matrix[0, 0]),
                    "fy": float(session.camera_matrix[1, 1]),
                },
                "principal_point_px": {
                    "cx": float(session.camera_matrix[0, 2]),
                    "cy": float(session.camera_matrix[1, 2]),
                },
                "sample_count": session.sample_count,
                "quality_report": session.quality_report,
                "param_std": session.param_std,
                "confidence": round(session.confidence, 3),
                "converged": session.converged,
            }
        else:
            calib = await asyncio.to_thread(session.run_calibration)
        finished = calib
        report = calib.get("quality_report") or session.quality_report or {}
        if calib.get("success") and report.get("pass"):
            try:
                saved_path = session.save(CALIB_SAVE_DIR)
                session.last_message = f"자동 캘리브레이션 완료 · 저장됨 ({os.path.basename(saved_path)})"
            except Exception as e:  # 저장 실패해도 계산 결과는 유지
                session.last_message = f"캘리브레이션 완료 — 저장 실패: {e}"
        elif calib.get("success"):
            session.last_message = "자동 캘리브레이션 완료 — 품질 미달로 저장 보류 (검토 후 수동 저장)"
        else:
            session.last_message = calib.get("message") or "자동 캘리브레이션 실패"
        session.auto_done = True
        session.auto_enabled = False

    return {
        "accepted": accepted,
        "sample_message": sample_message,
        "auto": {
            "detected": decision.get("detected"),
            "still_ticks": decision.get("still_ticks"),
            "motion_px": decision.get("motion_px"),
            "zone": decision.get("zone"),
            "reason": decision.get("reason"),
            **session.auto_state(),
        },
        "finished": finished,
        "saved_path": saved_path,
        "status": _session_status(session),
    }


@router.post("/run/{camera_id}")
async def run_calibration(camera_id: int):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    session = calibration_manager.get_session(camera_id)
    try:
        result = session.run_calibration()
    except cv2.error as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"OpenCV calibration failed: {str(e)}",
                "status": _session_status(session),
            },
        )
    status_code = 200 if result.get("success") else 400
    return JSONResponse(status_code=status_code, content={**result, "status": _session_status(session)})


@router.post("/save/{camera_id}")
async def save_calibration(camera_id: int, force: bool = False):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    session = calibration_manager.get_session(camera_id)
    try:
        path = session.save(CALIB_SAVE_DIR, force=force)
        return {
            "success": True,
            "message": "캘리브레이션 결과 저장됨",
            "path": path,
            "quality": session.quality_report,
        }
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
