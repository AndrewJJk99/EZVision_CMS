"""
CMS 측정 라우터 — 저장된 캘리브레이션으로 왜곡 보정 후 물체 엣지를 추출한다.

높이(단차) 환산은 깊이 정보(LUT/레이저/스테레오)가 필요하므로, 이 라우터는
"왜곡 보정 + 엣지/컨투어 추출 + 픽셀 계측"까지 담당한다. LUT가 준비되면
`_pixel_to_height()` 자리에 매핑을 연결하면 된다.
"""
import os
import sys

project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_path)

import asyncio
import base64
import glob
import json
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils.camera_grab_v2 import get_frame
from utils import laser_manager as lm

router = APIRouter(prefix="/measurement", tags=["measurement"])

CALIB_DIR = os.path.join(os.path.dirname(__file__), "..", "calibration_data")
FRAME_RETRY_COUNT = 25
FRAME_RETRY_DELAY_SEC = 0.08

# 캡처한 왜곡보정 프레임을 카메라별로 보관 → 레이저 튜닝/LUT가 같은 이미지를 사용
_FRAMES = {}


def _list_calib_files():
    return sorted(glob.glob(os.path.join(CALIB_DIR, "*.json")), reverse=True)


def _load_calibration(path: str):
    with open(path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    cm = np.array(meta["camera_matrix"], dtype=np.float64)
    dist = np.array(meta["dist_coeffs"], dtype=np.float64)
    size = (int(meta["image_size"]["width"]), int(meta["image_size"]["height"]))
    return meta, cm, dist, size


def _resolve_calibration(camera_id: int, calibration_file: Optional[str]):
    files = _list_calib_files()
    if calibration_file:
        path = os.path.join(CALIB_DIR, os.path.basename(calibration_file))
        return path if os.path.exists(path) else None

    # 해당 카메라의 최신 캘리브레이션 우선, 없으면 전체 최신
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                meta = json.load(fp)
            if meta.get("camera_id") == camera_id:
                return f
        except Exception:
            continue
    return files[0] if files else None


async def _fetch_bgr(camera_id: int, width: int, height: int):
    for attempt in range(FRAME_RETRY_COUNT):
        jpeg = await get_frame(camera_id, stream_width=width, stream_height=height)
        if jpeg:
            arr = np.frombuffer(jpeg, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                return img
        if attempt < FRAME_RETRY_COUNT - 1:
            await asyncio.sleep(FRAME_RETRY_DELAY_SEC)
    return None


def _b64_jpeg(img: np.ndarray) -> Optional[str]:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


async def _capture_undistorted(camera_id: int, calibration_file: Optional[str]):
    """반환: (undistorted_bgr, meta, error_response). 실패 시 앞 둘은 None."""
    path = _resolve_calibration(camera_id, calibration_file)
    if not path or not os.path.exists(path):
        return None, None, JSONResponse(
            status_code=404,
            content={"error": "저장된 캘리브레이션 결과가 없습니다. 먼저 캘리브레이션을 실행하세요."},
        )
    meta, cm, dist, (cw, ch) = _load_calibration(path)
    img = await _fetch_bgr(camera_id, cw, ch)
    if img is None:
        return None, None, JSONResponse(
            status_code=503,
            content={"error": "프레임을 가져올 수 없습니다 (Monitor·카메라 상태 확인)"},
        )
    if (img.shape[1], img.shape[0]) != (cw, ch):
        img = cv2.resize(img, (cw, ch), interpolation=cv2.INTER_AREA)
    undistorted = cv2.undistort(img, cm, dist)
    meta["_calibration_file"] = os.path.basename(path)
    return undistorted, meta, None


class HsvParams(BaseModel):
    h_low: int = Field(lm.DEFAULT_H_LOW, ge=0, le=179)
    h_high: int = Field(lm.DEFAULT_H_HIGH, ge=0, le=179)
    s_min: int = Field(lm.DEFAULT_S_MIN, ge=0, le=255)
    v_min: int = Field(lm.DEFAULT_V_MIN, ge=0, le=255)
    # 검출 방식: "auto"(밝기 자동) | "hsv"(색상 수동)
    method: str = Field("auto")
    blue_boost: bool = Field(True)
    thresh_offset: int = Field(0, ge=-100, le=100)
    # 반사광 자동 제거
    keep_largest: bool = Field(True)  # 가장 긴 선만 남김
    bridge_gap: int = Field(25, ge=1, le=400)  # 끊긴 선 이어붙이기(px)
    min_area: int = Field(30, ge=0, le=100000)
    peak_band: int = Field(12, ge=0, le=400)
    max_jump: float = Field(25.0, ge=0)
    roi_y0: Optional[int] = Field(None, ge=0)
    roi_y1: Optional[int] = Field(None, ge=0)


def _laser_kwargs(req: "HsvParams") -> dict:
    return {
        "method": req.method,
        "blue_boost": req.blue_boost,
        "thresh_offset": req.thresh_offset,
        "h_low": req.h_low,
        "h_high": req.h_high,
        "s_min": req.s_min,
        "v_min": req.v_min,
        "keep_largest": req.keep_largest,
        "bridge_gap": req.bridge_gap,
        "min_area": req.min_area,
        "peak_band": req.peak_band,
        "max_jump": req.max_jump,
        "roi_y0": req.roi_y0,
        "roi_y1": req.roi_y1,
    }


class CaptureRequest(BaseModel):
    calibration_file: Optional[str] = None


class LaserDetectRequest(HsvParams):
    calibration_file: Optional[str] = None
    use_stored: bool = False  # True면 새 캡처 없이 저장된 프레임 사용


class LutBuildRequest(BaseModel):
    increment_mm: float = Field(2.5, gt=0)
    base_mm: float = Field(0.0)
    reverse_order: bool = False
    min_width: int = Field(0, ge=0, le=500)  # 0=자동
    sensitivity: int = Field(50, ge=0, le=100)  # 단 경계 검출 민감도


class MeasureRequest(BaseModel):
    a_x0: int = Field(..., ge=0)
    a_x1: int = Field(..., ge=0)
    b_x0: int = Field(..., ge=0)
    b_x1: int = Field(..., ge=0)


class StepsRequest(BaseModel):
    reverse_order: bool = False
    min_width: int = Field(0, ge=0, le=500)  # 0=자동
    sensitivity: int = Field(50, ge=0, le=100)


class AnalyzeRequest(BaseModel):
    calibration_file: Optional[str] = Field(
        None, description="사용할 캘리브레이션 json 파일명 (없으면 최신 자동 선택)"
    )
    canny_low: int = Field(50, ge=0, le=500)
    canny_high: int = Field(150, ge=0, le=1000)
    blur_ksize: int = Field(5, ge=1, le=31)
    min_contour_area: int = Field(80, ge=0)


@router.get("/calibrations")
async def list_calibrations():
    items = []
    for path in _list_calib_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
        items.append(
            {
                "file": os.path.basename(path),
                "camera_id": meta.get("camera_id"),
                "ui_camera_id": meta.get("ui_camera_id"),
                "rms_error": meta.get("rms_error"),
                "square_size_mm": meta.get("square_size_mm"),
                "pattern_inner_corners": meta.get("pattern_inner_corners"),
                "image_size": meta.get("image_size"),
                "saved_at": meta.get("saved_at"),
            }
        )
    return {"calibrations": items}


@router.post("/analyze/{camera_id}")
async def analyze(camera_id: int, req: AnalyzeRequest = AnalyzeRequest()):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    path = _resolve_calibration(camera_id, req.calibration_file)
    if not path or not os.path.exists(path):
        return JSONResponse(
            status_code=404,
            content={"error": "저장된 캘리브레이션 결과가 없습니다. 먼저 캘리브레이션을 실행하세요."},
        )

    meta, cm, dist, (cw, ch) = _load_calibration(path)

    img = await _fetch_bgr(camera_id, cw, ch)
    if img is None:
        return JSONResponse(
            status_code=503,
            content={"error": "프레임을 가져올 수 없습니다 (Monitor·카메라 상태 확인)"},
        )

    # 캘리브레이션 시점 해상도에 맞춰야 내부 파라미터가 정확히 적용됨
    if (img.shape[1], img.shape[0]) != (cw, ch):
        img = cv2.resize(img, (cw, ch), interpolation=cv2.INTER_AREA)

    undistorted = cv2.undistort(img, cm, dist)

    gray = cv2.cvtColor(undistorted, cv2.COLOR_BGR2GRAY)
    k = int(req.blur_ksize) | 1  # 홀수 보정
    blurred = cv2.GaussianBlur(gray, (k, k), 0)
    edges = cv2.Canny(blurred, int(req.canny_low), int(req.canny_high))

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= req.min_contour_area]

    annotated = undistorted.copy()
    cv2.drawContours(annotated, contours, -1, (0, 255, 0), 1)

    bbox = None
    if contours:
        largest = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest)
        bbox = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 0, 255), 2)

    ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return JSONResponse(status_code=500, content={"error": "이미지 인코딩 실패"})
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")

    return {
        "image": f"data:image/jpeg;base64,{b64}",
        "calibration_file": os.path.basename(path),
        "rms_error": meta.get("rms_error"),
        "square_size_mm": meta.get("square_size_mm"),
        "edge_pixels": int(np.count_nonzero(edges)),
        "contour_count": len(contours),
        "bbox": bbox,
        "image_size": {"width": cw, "height": ch},
        "height_note": (
            "높이(단차) 환산은 깊이 정보가 필요합니다. LUT 준비 후 연결 예정 — "
            "현재는 왜곡 보정 + 엣지/컨투어 추출까지 제공합니다."
        ),
    }


# ─────────────────────────────────────────────────────────────
# 캡처: 왜곡보정 프레임 1장을 저장 (튜닝/LUT가 같은 이미지를 사용)
# ─────────────────────────────────────────────────────────────
@router.post("/capture/{camera_id}")
async def capture(camera_id: int, req: CaptureRequest = CaptureRequest()):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    undistorted, meta, err = await _capture_undistorted(camera_id, req.calibration_file)
    if err is not None:
        return err

    ch, cw = undistorted.shape[:2]
    _FRAMES[camera_id] = {
        "img": undistorted,
        "calibration_file": meta.get("_calibration_file"),
        "size": (cw, ch),
    }
    img_b64 = _b64_jpeg(undistorted)
    if img_b64 is None:
        return JSONResponse(status_code=500, content={"error": "이미지 인코딩 실패"})
    return {
        "image": img_b64,
        "calibration_file": meta.get("_calibration_file"),
        "image_size": {"width": int(cw), "height": int(ch)},
    }


# ─────────────────────────────────────────────────────────────
# 단계 A: 레이저 선 검출 → 점 목록 반환 (튜닝)
# ─────────────────────────────────────────────────────────────
@router.post("/laser/detect/{camera_id}")
async def laser_detect(camera_id: int, req: LaserDetectRequest = LaserDetectRequest()):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    stored = _FRAMES.get(camera_id)
    if req.use_stored and stored is not None:
        undistorted = stored["img"]
        calib_file = stored.get("calibration_file")
    else:
        undistorted, meta, err = await _capture_undistorted(camera_id, req.calibration_file)
        if err is not None:
            return err
        calib_file = meta.get("_calibration_file")

    profile, _mask = lm.detect_laser_profile(undistorted, **_laser_kwargs(req))
    points = lm.profile_to_points(profile)

    ch, cw = undistorted.shape[:2]
    # 캡처 프레임 + 검출 결과를 서버에 저장 → LUT/측정이 그대로 사용
    _FRAMES[camera_id] = {
        "img": undistorted,
        "profile": profile,
        "points": points,
        "calibration_file": calib_file,
        "size": (cw, ch),
    }

    overlay = lm.draw_points(undistorted, points)  # 검출된 선(가장 긴 것)만 표시
    img_b64 = _b64_jpeg(overlay)
    if img_b64 is None:
        return JSONResponse(status_code=500, content={"error": "이미지 인코딩 실패"})

    return {
        "image": img_b64,
        "valid_columns": len(points),
        "total_columns": int(cw),
        "coverage": round(len(points) / max(1, cw), 3),
        "calibration_file": calib_file,
        "image_size": {"width": int(cw), "height": int(ch)},
    }


# ─────────────────────────────────────────────────────────────
# 단계 B: 계단블록으로 LUT 생성 + 저장
# ─────────────────────────────────────────────────────────────
@router.post("/lut/build/{camera_id}")
async def lut_build(camera_id: int, req: LutBuildRequest = LutBuildRequest()):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    stored = _FRAMES.get(camera_id)
    if stored is None or stored.get("profile") is None:
        return JSONResponse(
            status_code=409,
            content={"error": "먼저 '캡처 & 검출'로 이미지를 캡처하세요 (같은 이미지로 LUT를 만듭니다)."},
        )

    undistorted = stored["img"]
    calib_file = stored.get("calibration_file")
    profile = stored.get("profile")
    points = lm.profile_to_points(profile) if profile is not None else (stored.get("points") or [])
    ch, cw = undistorted.shape[:2]

    table, build_err = lm.build_lut_auto(
        points,
        req.increment_mm,
        req.base_mm,
        req.reverse_order,
        req.min_width,
        req.sensitivity,
    )
    if build_err:
        return JSONResponse(status_code=422, content={"error": build_err})

    overlay = lm.draw_points(undistorted, points)
    for row in table:
        y = int(round(row["y_pixel"]))
        x = int(round(row["mean_x"]))
        cv2.line(overlay, (0, y), (cw - 1, y), (0, 0, 255), 1)
        cv2.putText(
            overlay,
            f'{row["height_mm"]}mm',
            (max(0, x - 30), max(12, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    path = lm.save_lut(
        CALIB_DIR,
        camera_id,
        table,
        {
            "calibration_file": calib_file,
            "increment_mm": req.increment_mm,
            "base_mm": req.base_mm,
            "reverse_order": req.reverse_order,
            "image_size": {"width": int(cw), "height": int(ch)},
        },
    )

    img_b64 = _b64_jpeg(overlay)
    return {
        "image": img_b64,
        "lut_file": os.path.basename(path),
        "table": table,
        "step_count": len(table),
        "image_size": {"width": int(cw), "height": int(ch)},
    }


# ─────────────────────────────────────────────────────────────
# 단계 C-2: 자동 단 분석 (계단 전체 검증) — 정리된 점 사용
# ─────────────────────────────────────────────────────────────
@router.post("/measure/steps/{camera_id}")
async def measure_steps(camera_id: int, req: StepsRequest = StepsRequest()):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    lut = lm.load_lut(CALIB_DIR, camera_id)
    if not lut:
        return JSONResponse(
            status_code=404, content={"error": "저장된 LUT가 없습니다. 먼저 LUT를 생성하세요."}
        )
    stored = _FRAMES.get(camera_id)
    if stored is None or stored.get("profile") is None:
        return JSONResponse(
            status_code=409,
            content={"error": "먼저 '측정 대상 캡처 & 검출'을 실행하세요."},
        )
    # LUT 생성과 동일: 저장된 profile → points (points만 쓰면 불일치 가능)
    profile = stored["profile"]
    points = lm.profile_to_points(profile)
    if len(points) < 20:
        return JSONResponse(
            status_code=422,
            content={"error": "레이저 점이 너무 적습니다. 먼저 캡처 & 검출을 다시 실행하세요."},
        )

    lut_path = lm._lut_path(CALIB_DIR, camera_id)
    lut_range = lm.lut_y_range(lut)

    clusters, err = None, None
    used_sensitivity = req.sensitivity
    for sens in sorted(set([req.sensitivity, min(100, req.sensitivity + 20), min(100, req.sensitivity + 40), 100])):
        clusters, err = lm.auto_segment_steps(
            points, min_width=req.min_width, sensitivity=sens
        )
        if err:
            continue
        if len(clusters) >= 2:
            used_sensitivity = sens
            break
    if err and (clusters is None or len(clusters) < 2):
        return JSONResponse(status_code=422, content={"error": err})
    if clusters is None or len(clusters) < 2:
        return JSONResponse(
            status_code=422,
            content={"error": "단을 2개 이상 찾지 못했습니다 (레이저 선·계단 전체가 화면에 들어오는지 확인)"},
        )
    if req.reverse_order:
        clusters = list(reversed(clusters))

    steps = []
    for i, c in enumerate(clusters):
        h = lm.y_to_height(lut, c["y_pixel"])
        steps.append(
            {
                "index": i + 1,
                "mean_x": c["mean_x"],
                "y_pixel": c["y_pixel"],
                "height_mm": None if h is None else round(h, 4),
                "count": c["count"],
            }
        )

    diffs = []
    for i in range(len(steps) - 1):
        a = steps[i]["height_mm"]
        b = steps[i + 1]["height_mm"]
        diffs.append(None if a is None or b is None else round(b - a, 4))

    payload = {
        "steps": steps,
        "diffs": diffs,
        "lut_created_at": lut.get("created_at"),
        "lut_file": os.path.basename(lut_path),
        "lut_table": lut.get("table"),
        "lut_y_range": lut_range,
        "used_sensitivity": used_sensitivity,
        "detected_points": len(points),
    }

    if stored is not None:
        overlay = lm.draw_points(stored["img"], points)
        ch, cw = stored["img"].shape[:2]
        for s in steps:
            y = int(round(s["y_pixel"]))
            x = int(round(s["mean_x"]))
            cv2.line(overlay, (0, y), (cw - 1, y), (0, 0, 255), 1)
            label = (
                f'{s["index"]}: {s["height_mm"]}mm'
                if s["height_mm"] is not None
                else f'{s["index"]}'
            )
            cv2.putText(
                overlay, label, (max(0, x - 30), max(12, y - 4)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
            )
        img_b64 = _b64_jpeg(overlay)
        if img_b64:
            payload["image"] = img_b64
        payload["image_size"] = {"width": int(cw), "height": int(ch)}

    return payload


@router.get("/lut/{camera_id}")
async def lut_get(camera_id: int):
    lut = lm.load_lut(CALIB_DIR, camera_id)
    if not lut:
        return JSONResponse(
            status_code=404, content={"error": "저장된 LUT가 없습니다. 먼저 LUT를 생성하세요."}
        )
    return lut


# ─────────────────────────────────────────────────────────────
# 단계 C: 실제 측정 (두 구간 단차)
# ─────────────────────────────────────────────────────────────
@router.post("/measure/{camera_id}")
async def measure(camera_id: int, req: MeasureRequest):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    lut = lm.load_lut(CALIB_DIR, camera_id)
    if not lut:
        return JSONResponse(
            status_code=404, content={"error": "저장된 LUT가 없습니다. 먼저 LUT를 생성하세요."}
        )

    stored = _FRAMES.get(camera_id)
    if stored is None or stored.get("profile") is None:
        return JSONResponse(
            status_code=409,
            content={"error": "먼저 '측정 대상 캡처 & 검출'을 실행하세요."},
        )
    undistorted = stored["img"]
    profile = stored["profile"]
    ch, cw = undistorted.shape[:2]

    y_a = lm.region_mean_y(profile, req.a_x0, req.a_x1)
    y_b = lm.region_mean_y(profile, req.b_x0, req.b_x1)
    if y_a is None or y_b is None:
        return JSONResponse(
            status_code=422,
            content={"error": "선택한 구간에서 레이저를 검출하지 못했습니다 (구간/점 확인)"},
        )

    h_a = lm.y_to_height(lut, y_a)
    h_b = lm.y_to_height(lut, y_b)
    if h_a is None or h_b is None:
        return JSONResponse(status_code=422, content={"error": "LUT 보간 실패"})

    lut_path = lm._lut_path(CALIB_DIR, camera_id)
    lut_range = lm.lut_y_range(lut)

    overlay = lm.draw_profile(undistorted, profile)

    def _mark(x0, x1, y, color, label):
        x0, x1 = sorted((int(x0), int(x1)))
        cv2.rectangle(overlay, (x0, 0), (x1, ch - 1), color, 1)
        yy = int(round(y))
        cv2.line(overlay, (x0, yy), (x1, yy), color, 2)
        cv2.putText(
            overlay, label, (x0, max(14, yy - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA,
        )

    _mark(req.a_x0, req.a_x1, y_a, (0, 255, 0), f"A {h_a:.3f}mm")
    _mark(req.b_x0, req.b_x1, y_b, (0, 0, 255), f"B {h_b:.3f}mm")

    img_b64 = _b64_jpeg(overlay)
    return {
        "image": img_b64,
        "height_a_mm": round(h_a, 4),
        "height_b_mm": round(h_b, 4),
        "step_diff_mm": round(abs(h_a - h_b), 4),
        "y_a": round(y_a, 2),
        "y_b": round(y_b, 2),
        "lut_file": os.path.basename(lut_path),
        "lut_y_range": lut_range,
        "lut_created_at": lut.get("created_at"),
        "image_size": {"width": int(cw), "height": int(ch)},
    }
