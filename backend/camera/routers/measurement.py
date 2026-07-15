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

from utils.camera_grab_v2 import get_frame_bgr
from utils import laser_manager as lm
from utils.calibration_manager import (
    CalibrationConfig,
    CalibrationSession,
    DEFAULT_INNER_COLS,
    DEFAULT_INNER_ROWS,
    DEFAULT_SQUARE_MM,
    undistort_bgr,
)

router = APIRouter(prefix="/measurement", tags=["measurement"])

CALIB_DIR = os.path.join(os.path.dirname(__file__), "..", "calibration_data")
FRAME_RETRY_COUNT = 25
FRAME_RETRY_DELAY_SEC = 0.08

# 캡처한 왜곡보정 프레임을 카메라별로 보관 → 레이저 튜닝/LUT가 같은 이미지를 사용
_FRAMES = {}


def _list_calib_files():
    return sorted(glob.glob(os.path.join(CALIB_DIR, "camera_*_calib_*.json")), reverse=True)


def _load_calibration(path: str):
    with open(path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    cm = np.array(meta["camera_matrix"], dtype=np.float64)
    dist = np.array(meta["dist_coeffs"], dtype=np.float64)
    size = (int(meta["image_size"]["width"]), int(meta["image_size"]["height"]))
    distortion_model = meta.get("distortion_model") or "brown5"
    return meta, cm, dist, size, distortion_model


def _undistort(img: np.ndarray, cm, dist, distortion_model: str) -> np.ndarray:
    return undistort_bgr(img, cm, dist, distortion_model)


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


async def _fetch_bgr(camera_id: int):
    """카메라 원본 해상도 BGR (축소 없음)."""
    for attempt in range(FRAME_RETRY_COUNT):
        img = await get_frame_bgr(camera_id)
        if img is not None:
            return img
        if attempt < FRAME_RETRY_COUNT - 1:
            await asyncio.sleep(FRAME_RETRY_DELAY_SEC)
    return None


def _size_mismatch_error(frame_w: int, frame_h: int, calib_w: int, calib_h: int):
    return JSONResponse(
        status_code=409,
        content={
            "error": (
                f"프레임 해상도({frame_w}×{frame_h})와 캘리브레이션({calib_w}×{calib_h})이 다릅니다. "
                "원본 해상도로 캘리브레이션을 다시 실행·저장하세요."
            ),
        },
    )


def _b64_jpeg(img: np.ndarray) -> Optional[str]:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _crop_to_laser(
    img: np.ndarray,
    points: list,
    margin_y: int = 90,
    margin_x: int = 40,
):
    """오버레이 이미지를 레이저 영역으로 잘라 확대 효과를 준다.

    반환: (cropped_img, rect) — rect는 (x0, y0, x1, y1) 원본 기준 crop 사각형.
    검출 결과가 없거나 너무 작으면 (원본, None)을 반환한다.
    """
    pts = [p for p in (points or []) if p is not None]
    if not pts:
        return img, None
    h, w = img.shape[:2]
    xs = [int(round(p[0])) for p in pts]
    ys = [int(round(p[1])) for p in pts]
    x0 = max(0, min(xs) - margin_x)
    x1 = min(w, max(xs) + margin_x)
    # 위쪽은 단 높이 텍스트 공간까지 고려해 더 넉넉히
    y0 = max(0, min(ys) - (margin_y + 40))
    y1 = min(h, max(ys) + margin_y)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return img, None
    return img[y0:y1, x0:x1], (int(x0), int(y0), int(x1), int(y1))


def _overlay_payload(overlay: np.ndarray, points: list) -> dict:
    """오버레이 이미지를 확대본(image)+원본(image_full)+crop 사각형으로 인코딩."""
    cropped, rect = _crop_to_laser(overlay, points)
    out = {
        "image": _b64_jpeg(cropped),
        "image_full": _b64_jpeg(overlay),
    }
    if rect is not None:
        out["crop"] = {"x0": rect[0], "y0": rect[1], "x1": rect[2], "y1": rect[3]}
    return out


def _resolve_gap_mm_per_px(
    camera_id: int,
    req_mm: Optional[float],
    use_saved: bool,
    calibration_file: Optional[str] = None,
):
    """(mm_per_px, scale_meta). 요청값 → 캘리브 plane_scale → gap_scale.json."""
    if req_mm is not None and float(req_mm) > 0:
        return float(req_mm), {"source": "request"}
    if use_saved:
        # 1) 선택한 캘리브레이션 JSON의 plane_scale
        calib_path = _resolve_calibration(camera_id, calibration_file)
        if calib_path:
            ps = lm.load_plane_scale_from_calibration(
                CALIB_DIR, os.path.basename(calib_path)
            )
            if ps and ps.get("mm_per_px"):
                return float(ps["mm_per_px"]), {
                    "source": "calibration",
                    "saved_at": ps.get("saved_at"),
                    "square_px": ps.get("square_px"),
                    "square_px_x": ps.get("square_px_x"),
                    "square_size_mm": ps.get("square_size_mm"),
                    "calibration_file": os.path.basename(calib_path),
                }
        # 2) 레거시 camera_*_gap_scale.json
        saved = lm.load_gap_scale(CALIB_DIR, camera_id)
        if saved and saved.get("mm_per_px"):
            return float(saved["mm_per_px"]), {
                "source": "saved",
                "saved_at": saved.get("saved_at"),
                "square_px": saved.get("square_px"),
                "square_px_x": saved.get("square_px_x"),
                "square_size_mm": saved.get("square_size_mm"),
                "calibration_file": saved.get("calibration_file"),
            }
    return None, {"source": None}

async def _capture_undistorted(camera_id: int, calibration_file: Optional[str]):
    """반환: (undistorted_bgr, meta, error_response). 실패 시 앞 둘은 None."""
    path = _resolve_calibration(camera_id, calibration_file)
    if not path or not os.path.exists(path):
        return None, None, JSONResponse(
            status_code=404,
            content={"error": "저장된 캘리브레이션 결과가 없습니다. 먼저 캘리브레이션을 실행하세요."},
        )
    meta, cm, dist, (cw, ch), distortion_model = _load_calibration(path)
    img = await _fetch_bgr(camera_id)
    if img is None:
        return None, None, JSONResponse(
            status_code=503,
            content={"error": "프레임을 가져올 수 없습니다 (Monitor·카메라 상태 확인)"},
        )
    fh, fw = img.shape[:2]
    if (fw, fh) != (cw, ch):
        return None, None, _size_mismatch_error(fw, fh, cw, ch)
    undistorted = _undistort(img, cm, dist, distortion_model)
    meta["_calibration_file"] = os.path.basename(path)
    return undistorted, meta, None


class LaserDetectParams(BaseModel):
    """강건 자동 검출 옵션. 노이즈 임계값은 검출기가 장면에서 결정한다."""
    roi_y0: Optional[int] = Field(None, ge=0)
    roi_y1: Optional[int] = Field(None, ge=0)
    laser_color: str = Field("blue", description="레이저 색: blue | red")


def _laser_kwargs(req: "LaserDetectParams") -> dict:
    color = str(getattr(req, "laser_color", "blue") or "blue").lower()
    if color not in ("blue", "red"):
        color = "blue"
    return {
        "roi_y0": req.roi_y0,
        "roi_y1": req.roi_y1,
        "laser_color": color,
    }


class CaptureRequest(BaseModel):
    calibration_file: Optional[str] = None


class LaserDetectRequest(LaserDetectParams):
    calibration_file: Optional[str] = None
    use_stored: bool = False  # True면 새 캡처 없이 저장된 프레임 사용
    detect_mode: str = Field(
        "default",
        description="default | lut | gap — lut는 계단 LUT용 고정밀 검출",
    )


class LutImageDetectRequest(LaserDetectParams):
    lut_file: Optional[str] = None
    image_file: Optional[str] = None


class LutBuildRequest(BaseModel):
    increment_mm: float = Field(2.5, gt=0)
    base_mm: float = Field(0.0)
    reverse_order: bool = False
    min_width: int = Field(0, ge=0, le=500)  # 0=자동
    sensitivity: int = Field(35, ge=0, le=100)  # 단 경계 검출 민감도 (낮을수록 과다 분할↓)
    frame_count: int = Field(1, ge=1, le=10)  # LUT용 profile 병합 프레임 수
    edge_margin_ratio: float = Field(0.10, ge=0.0, le=0.45)
    trim_ratio: float = Field(0.10, ge=0.0, le=0.35)
    lut_name: Optional[str] = Field(None, max_length=64)
    save: bool = Field(False, description="True면 생성과 동시에 파일 저장. False면 미리보기만")


class LutSaveRequest(BaseModel):
    lut_name: Optional[str] = Field(None, max_length=64)


class RoiRect(BaseModel):
    x0: int = Field(..., ge=0)
    y0: int = Field(..., ge=0)
    x1: int = Field(..., ge=0)
    y1: int = Field(..., ge=0)


class MeasureRequest(BaseModel):
    a_x0: Optional[int] = Field(None, ge=0)
    a_x1: Optional[int] = Field(None, ge=0)
    b_x0: Optional[int] = Field(None, ge=0)
    b_x1: Optional[int] = Field(None, ge=0)
    a_roi: Optional[RoiRect] = None
    b_roi: Optional[RoiRect] = None
    lut_file: Optional[str] = None


class StepsRequest(BaseModel):
    reverse_order: bool = False
    min_width: int = Field(0, ge=0, le=500)  # 0=자동
    sensitivity: int = Field(50, ge=0, le=100)
    lut_file: Optional[str] = None


class GapMeasureRequest(LaserDetectParams):
    """간격 측정: 레이저 직선 끝점 사이 거리."""
    calibration_file: Optional[str] = None
    use_stored: bool = False  # True면 저장된 프레임 재사용(재검출은 gap 전용)
    redetect: bool = True  # True면 gap용 검출(끊김 보존) 재실행
    mm_per_px: Optional[float] = Field(
        None, gt=0, description="가로 스케일(mm/px). 없으면 저장된 gap scale 사용, 그것도 없으면 px만"
    )
    use_saved_scale: bool = Field(
        True, description="mm_per_px 미지정 시 캘리브 plane_scale(또는 레거시 gap_scale) 사용"
    )
    min_segment_px: int = Field(lm.DEFAULT_GAP_MIN_SEGMENT_PX, ge=3, le=500)
    max_nan_bridge: int = Field(lm.DEFAULT_GAP_MAX_NAN_BRIDGE, ge=0, le=20)
    fit_len: int = Field(lm.DEFAULT_GAP_FIT_LEN, ge=3, le=80)
    min_gap_px: float = Field(lm.DEFAULT_GAP_MIN_PX, ge=0.5, le=2000)
    max_gap_px: float = Field(lm.DEFAULT_GAP_MAX_PX, ge=1, le=5000)
    search_x0: Optional[int] = Field(None, ge=0)
    search_x1: Optional[int] = Field(None, ge=0)
    min_step_dy_px: Optional[float] = Field(
        None, ge=0, le=500, description="자동 모드에서 이 이상 y가 다른(다른 단) 세그먼트 쌍만 후보로 사용"
    )
    a_roi: Optional[RoiRect] = None
    b_roi: Optional[RoiRect] = None


class GapScaleRequest(BaseModel):
    """측정면과 같은 거리에 둔 체커보드로 mm/px = square_mm / square_px 계산."""
    calibration_file: Optional[str] = None
    inner_cols: Optional[int] = Field(None, ge=2, le=40)
    inner_rows: Optional[int] = Field(None, ge=2, le=40)
    square_size_mm: Optional[float] = Field(None, gt=0)
    save: bool = Field(
        True,
        description="계산 결과를 캘리브레이션 JSON(plane_scale)에 함께 저장",
    )


class AnalyzeRequest(BaseModel):
    calibration_file: Optional[str] = Field(
        None, description="사용할 캘리브레이션 json 파일명 (없으면 최신 자동 선택)"
    )
    canny_low: int = Field(50, ge=0, le=500)
    canny_high: int = Field(150, ge=0, le=1000)
    blur_ksize: int = Field(5, ge=1, le=31)
    min_contour_area: int = Field(80, ge=0)


@router.get("/luts")
async def list_luts():
    items = []
    for path in lm.list_lut_files(CALIB_DIR):
        try:
            with open(path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
        table = meta.get("table") or []
        y_range = lm.lut_y_range(meta)
        fname = os.path.basename(path)
        items.append(
            {
                "file": fname,
                "camera_id": meta.get("camera_id"),
                "created_at": meta.get("created_at"),
                "step_count": meta.get("step_count") or len(table),
                "increment_mm": meta.get("increment_mm"),
                "base_mm": meta.get("base_mm"),
                "reverse_order": meta.get("reverse_order"),
                "sensitivity": meta.get("sensitivity"),
                "lut_name": lm.lut_display_name(meta, fname),
                "calibration_file": meta.get("calibration_file"),
                "image_file": meta.get("image_file"),
                "image_exists": bool(
                    meta.get("image_file")
                    and os.path.exists(os.path.join(CALIB_DIR, os.path.basename(meta.get("image_file"))))
                ),
                "y_range": y_range,
            }
        )
    return {"luts": items}


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
                "distortion_model": meta.get("distortion_model") or "brown5",
                "quality_level": (meta.get("quality") or {}).get("level"),
                "quality_pass": (meta.get("quality") or {}).get("pass"),
                "square_size_mm": meta.get("square_size_mm"),
                "pattern_inner_corners": meta.get("pattern_inner_corners"),
                "image_size": meta.get("image_size"),
                "saved_at": meta.get("saved_at"),
                "plane_scale": meta.get("plane_scale"),
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

    meta, cm, dist, (cw, ch), distortion_model = _load_calibration(path)

    img = await _fetch_bgr(camera_id)
    if img is None:
        return JSONResponse(
            status_code=503,
            content={"error": "프레임을 가져올 수 없습니다 (Monitor·카메라 상태 확인)"},
        )

    fh, fw = img.shape[:2]
    if (fw, fh) != (cw, ch):
        return _size_mismatch_error(fw, fh, cw, ch)

    undistorted = _undistort(img, cm, dist, distortion_model)

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

    laser_kw = _laser_kwargs(req)
    mode = (req.detect_mode or "default").lower()
    if mode == "lut":
        profile, _mask, laser_quality = lm.detect_laser_profile_for_lut(
            undistorted,
            **laser_kw,
            return_quality=True,
        )
        laser_kw = {**laser_kw, "detect_mode": "lut"}
    elif mode == "gap":
        profile, _mask, laser_quality = lm.detect_laser_profile_for_gap(
            undistorted,
            **laser_kw,
            return_quality=True,
        )
        laser_kw = {**laser_kw, "detect_mode": "gap"}
    else:
        profile, _mask, laser_quality = lm.detect_laser_profile(
            undistorted,
            **laser_kw,
            return_quality=True,
        )

    points = lm.profile_to_points(profile)

    ch, cw = undistorted.shape[:2]
    # 캡처 프레임 + 검출 결과를 서버에 저장 → LUT/측정이 그대로 사용
    _FRAMES[camera_id] = {
        "img": undistorted,
        "profile": profile,
        "points": points,
        "laser_kwargs": laser_kw,
        "calibration_file": calib_file,
        "size": (cw, ch),
        "detect_mode": mode,
    }

    overlay = lm.draw_points(undistorted, points, radius=3, thickness=5)  # 검출선(굵게)
    images = _overlay_payload(overlay, points)  # 확대본 + 원본
    if images.get("image") is None:
        return JSONResponse(status_code=500, content={"error": "이미지 인코딩 실패"})

    return {
        **images,
        "valid_columns": len(points),
        "total_columns": int(cw),
        "coverage": round(len(points) / max(1, cw), 3),
        "calibration_file": calib_file,
        "image_size": {"width": int(cw), "height": int(ch)},
        "detector": (laser_quality or {}).get("detector", "robust_blue_ridge_v2"),
        "laser_color": laser_kw.get("laser_color", "blue"),
        "laser_quality": laser_quality,
    }


@router.post("/lut/image/detect/{camera_id}")
async def lut_image_detect(camera_id: int, req: LutImageDetectRequest = LutImageDetectRequest()):
    """저장된 LUT 생성 이미지를 사용해 카메라 캡처 없이 레이저를 재검출."""
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    lut = lm.load_lut(CALIB_DIR, camera_id, req.lut_file)
    if not lut:
        return JSONResponse(
            status_code=404,
            content={"error": "저장된 LUT가 없습니다. 먼저 LUT를 생성하세요."},
        )

    image_file = os.path.basename(req.image_file or lut.get("image_file") or "")
    if not image_file:
        return JSONResponse(
            status_code=404,
            content={"error": "선택한 LUT에 저장된 이미지가 없습니다. LUT를 다시 생성하세요."},
        )
    image_path = os.path.join(CALIB_DIR, image_file)
    if not os.path.exists(image_path):
        return JSONResponse(
            status_code=404,
            content={"error": f"저장된 LUT 이미지를 찾을 수 없습니다: {image_file}"},
        )

    undistorted = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if undistorted is None:
        return JSONResponse(status_code=500, content={"error": "저장 이미지 로드 실패"})

    profile, _mask, laser_quality = lm.detect_laser_profile_for_lut(
        undistorted,
        **_laser_kwargs(req),
        return_quality=True,
    )
    points = lm.profile_to_points(profile)
    ch, cw = undistorted.shape[:2]
    _FRAMES[camera_id] = {
        "img": undistorted,
        "profile": profile,
        "points": points,
        "laser_kwargs": _laser_kwargs(req),
        "calibration_file": lut.get("calibration_file"),
        "lut_file": lut.get("_lut_file"),
        "image_file": image_file,
        "size": (cw, ch),
    }

    overlay = lm.draw_points(undistorted, points, radius=3, thickness=5)
    images = _overlay_payload(overlay, points)
    if images.get("image") is None:
        return JSONResponse(status_code=500, content={"error": "이미지 인코딩 실패"})
    return {
        **images,
        "valid_columns": len(points),
        "total_columns": int(cw),
        "coverage": round(len(points) / max(1, cw), 3),
        "calibration_file": lut.get("calibration_file"),
        "lut_file": lut.get("_lut_file"),
        "image_file": image_file,
        "image_size": {"width": int(cw), "height": int(ch)},
        "detector": (laser_quality or {}).get("detector", "robust_blue_ridge_v2"),
        "laser_color": _laser_kwargs(req).get("laser_color", "blue"),
        "laser_quality": laser_quality,
    }


# ─────────────────────────────────────────────────────────────
# 단계 B: 계단블록으로 LUT 생성 (기본: 미리보기만, 저장은 별도)
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
    ch, cw = undistorted.shape[:2]

    profiles = [profile] if profile is not None else []
    laser_kwargs = dict(stored.get("laser_kwargs") or {})
    detect_mode = (stored.get("detect_mode") or laser_kwargs.get("detect_mode") or "default").lower()
    requested_frames = int(req.frame_count)
    captured_frames = 1 if profiles else 0
    for _ in range(max(0, requested_frames - captured_frames)):
        next_img, _meta, err = await _capture_undistorted(camera_id, calib_file)
        if err is not None:
            return err
        if detect_mode == "lut":
            next_profile, _mask = lm.detect_laser_profile_for_lut(next_img, **laser_kwargs)
        else:
            next_profile, _mask = lm.detect_laser_profile(next_img, **laser_kwargs)
        profiles.append(next_profile)
        captured_frames += 1

    if len(profiles) > 1:
        merged_profile = lm.merge_profiles_median(profiles)
        if merged_profile is not None:
            profile = merged_profile
            _FRAMES[camera_id]["profile"] = profile

    # 프레임 병합 뒤에도 동일 표면의 짧은 누락만 복원한다.
    if detect_mode == "lut" and profile is not None:
        profile = lm._clean_profile_without_breaking_steps(profile, preserve_gaps=False)
        _FRAMES[camera_id]["profile"] = profile

    points = lm.profile_to_points(profile) if profile is not None else (stored.get("points") or [])
    _FRAMES[camera_id]["points"] = points

    table, build_err = lm.build_lut_auto(
        points,
        req.increment_mm,
        req.base_mm,
        req.reverse_order,
        req.min_width,
        req.sensitivity,
        req.edge_margin_ratio,
        req.trim_ratio,
    )
    if build_err:
        return JSONResponse(status_code=422, content={"error": build_err})

    overlay = lm.draw_points(undistorted, points, radius=3, thickness=5)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.1
    for row in table:
        y = int(round(row["y_pixel"]))
        x = int(round(row["mean_x"]))
        cv2.line(overlay, (0, y), (cw - 1, y), (0, 0, 255), 2)
        text = f'{row["height_mm"]}mm'
        (tw, th), _ = cv2.getTextSize(text, font, font_scale, 3)
        tx = int(min(max(0, x - tw // 2), max(0, cw - tw)))
        ty = int(max(th + 6, y - 10))
        # 흰색 외곽선 + 검정 본문(어떤 배경에서도 또렷하게)
        cv2.putText(overlay, text, (tx, ty), font, font_scale, (255, 255, 255), 6, cv2.LINE_AA)
        cv2.putText(overlay, text, (tx, ty), font, font_scale, (0, 0, 0), 2, cv2.LINE_AA)

    lut_name = (req.lut_name or "").strip() or None
    if lut_name and not lm._sanitize_lut_slug(lut_name):
        return JSONResponse(status_code=422, content={"error": "LUT 이름에 사용할 수 있는 문자가 없습니다."})

    draft_meta = {
        "calibration_file": calib_file,
        "increment_mm": req.increment_mm,
        "base_mm": req.base_mm,
        "reverse_order": req.reverse_order,
        "sensitivity": req.sensitivity,
        "frame_count": captured_frames,
        "edge_margin_ratio": req.edge_margin_ratio,
        "trim_ratio": req.trim_ratio,
        "laser_detect": laser_kwargs,
        "lut_name": lut_name,
        "image_size": {"width": int(cw), "height": int(ch)},
    }
    _FRAMES[camera_id]["lut_draft"] = {
        "table": table,
        "meta": draft_meta,
        "img": undistorted,
    }

    saved = False
    lut_file = None
    image_file = None
    if req.save:
        path = lm.save_lut(CALIB_DIR, camera_id, table, draft_meta)
        lut_file = os.path.basename(path)
        image_file = f"{os.path.splitext(lut_file)[0]}.jpg"
        image_path = os.path.join(CALIB_DIR, image_file)
        ok = cv2.imwrite(image_path, undistorted, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if ok:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                payload["image_file"] = image_file
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        else:
            image_file = None
        saved = True

    return {
        **_overlay_payload(overlay, points),
        "saved": saved,
        "lut_file": lut_file,
        "lut_name": lut_name,
        "image_file": image_file,
        "table": table,
        "step_count": len(table),
        "frame_count": captured_frames,
        "edge_margin_ratio": req.edge_margin_ratio,
        "trim_ratio": req.trim_ratio,
        "image_size": {"width": int(cw), "height": int(ch)},
    }


@router.post("/lut/save/{camera_id}")
async def lut_save(camera_id: int, req: LutSaveRequest = LutSaveRequest()):
    """미리보기(생성)된 LUT draft를 파일로 저장."""
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    stored = _FRAMES.get(camera_id) or {}
    draft = stored.get("lut_draft")
    if not draft or not draft.get("table"):
        return JSONResponse(
            status_code=409,
            content={"error": "저장할 LUT가 없습니다. 먼저 'LUT 생성'을 실행하세요."},
        )

    lut_name = (req.lut_name or "").strip() or None
    if lut_name is None:
        lut_name = (draft.get("meta") or {}).get("lut_name")
    if lut_name and not lm._sanitize_lut_slug(lut_name):
        return JSONResponse(status_code=422, content={"error": "LUT 이름에 사용할 수 있는 문자가 없습니다."})

    meta = dict(draft.get("meta") or {})
    meta["lut_name"] = lut_name
    table = draft["table"]
    undistorted = draft.get("img")
    if undistorted is None:
        undistorted = stored.get("img")

    path = lm.save_lut(CALIB_DIR, camera_id, table, meta)
    lut_file = os.path.basename(path)
    image_file = None
    if undistorted is not None:
        image_file = f"{os.path.splitext(lut_file)[0]}.jpg"
        image_path = os.path.join(CALIB_DIR, image_file)
        ok = cv2.imwrite(image_path, undistorted, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if ok:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                payload["image_file"] = image_file
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        else:
            image_file = None

    return {
        "saved": True,
        "lut_file": lut_file,
        "lut_name": lut_name,
        "image_file": image_file,
        "table": table,
        "step_count": len(table),
    }


@router.delete("/lut/{camera_id}")
async def lut_delete(camera_id: int, lut_file: str):
    """저장된 LUT json과 연결 이미지를 삭제."""
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})
    ok, err, info = lm.delete_lut(CALIB_DIR, camera_id, lut_file)
    if not ok:
        return JSONResponse(status_code=404 if "찾을 수 없" in (err or "") else 422, content={"error": err})
    return {"deleted": True, **info}


# ─────────────────────────────────────────────────────────────
# 단계 C-2: 자동 단 분석 (계단 전체 검증) — 정리된 점 사용
# ─────────────────────────────────────────────────────────────
@router.post("/measure/steps/{camera_id}")
async def measure_steps(camera_id: int, req: StepsRequest = StepsRequest()):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    lut = lm.load_lut(CALIB_DIR, camera_id, req.lut_file)
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

    lut_path = lm.resolve_lut_path(CALIB_DIR, camera_id, req.lut_file or lut.get("_lut_file"))
    lut_range = lm.lut_y_range(lut)

    candidates = []
    err = None
    for sens in [10, 20, 30, 40, 50, 60, 70]:
        found, found_err = lm.auto_segment_steps(
            points,
            min_width=req.min_width,
            sensitivity=sens,
            y_merge_thr=4.0,
            max_plateau_std=4.0,
        )
        if found_err or not found or not (2 <= len(found) <= 12):
            err = found_err or err
            continue
        mean_std = float(np.mean([float(c.get("std_px") or 0) for c in found]))
        mean_coverage = float(np.mean([float(c.get("coverage") or 0) for c in found]))
        candidates.append((len(found), mean_std, mean_coverage, sens, found))

    if not candidates:
        return JSONResponse(
            status_code=422,
            content={"error": err or "안정적인 단을 2개 이상 찾지 못했습니다 (레이저 선·계단 전체 확인)"},
        )
    frequency = {}
    for n, *_rest in candidates:
        frequency[n] = frequency.get(n, 0) + 1
    _n, _std, _coverage, used_sensitivity, clusters = min(
        candidates,
        key=lambda item: (-frequency[item[0]], item[1], -item[2]),
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
        overlay = lm.draw_points(stored["img"], points, radius=3, thickness=5)
        ch, cw = stored["img"].shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.1
        for s in steps:
            y = int(round(s["y_pixel"]))
            x = int(round(s["mean_x"]))
            cv2.line(overlay, (0, y), (cw - 1, y), (0, 0, 255), 2)
            label = (
                f'{s["index"]}: {s["height_mm"]}mm'
                if s["height_mm"] is not None
                else f'{s["index"]}'
            )
            (tw, th), _ = cv2.getTextSize(label, font, font_scale, 3)
            tx = int(min(max(0, x - tw // 2), max(0, cw - tw)))
            ty = int(max(th + 6, y - 10))
            cv2.putText(overlay, label, (tx, ty), font, font_scale, (255, 255, 255), 6, cv2.LINE_AA)
            cv2.putText(overlay, label, (tx, ty), font, font_scale, (0, 0, 0), 2, cv2.LINE_AA)
        images = _overlay_payload(overlay, points)
        if images.get("image"):
            payload.update(images)
        payload["image_size"] = {"width": int(cw), "height": int(ch)}

    return payload


@router.get("/lut/{camera_id}")
async def lut_get(camera_id: int, lut_file: Optional[str] = None):
    lut = lm.load_lut(CALIB_DIR, camera_id, lut_file)
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

    lut = lm.load_lut(CALIB_DIR, camera_id, req.lut_file)
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

    if req.a_roi is not None and req.b_roi is not None:
        y_a = lm.roi_median_y(profile, req.a_roi.x0, req.a_roi.y0, req.a_roi.x1, req.a_roi.y1)
        y_b = lm.roi_median_y(profile, req.b_roi.x0, req.b_roi.y0, req.b_roi.x1, req.b_roi.y1)
        measure_mode = "roi"
    elif None not in (req.a_x0, req.a_x1, req.b_x0, req.b_x1):
        y_a = lm.region_mean_y(profile, req.a_x0, req.a_x1)
        y_b = lm.region_mean_y(profile, req.b_x0, req.b_x1)
        measure_mode = "x_range"
    else:
        return JSONResponse(
            status_code=422,
            content={"error": "A/B ROI 또는 A/B X 구간을 지정하세요."},
        )
    if y_a is None or y_b is None:
        return JSONResponse(
            status_code=422,
            content={"error": "선택한 A/B 영역에서 레이저를 검출하지 못했습니다 (ROI/레이저 점 확인)"},
        )

    h_a = lm.y_to_height(lut, y_a)
    h_b = lm.y_to_height(lut, y_b)
    if h_a is None or h_b is None:
        return JSONResponse(status_code=422, content={"error": "LUT 보간 실패"})

    lut_path = lm.resolve_lut_path(CALIB_DIR, camera_id, req.lut_file or lut.get("_lut_file"))
    lut_range = lm.lut_y_range(lut)

    overlay = lm.draw_profile(undistorted, profile)

    def _mark_range(x0, x1, y, color, label):
        x0, x1 = sorted((int(x0), int(x1)))
        cv2.rectangle(overlay, (x0, 0), (x1, ch - 1), color, 1)
        yy = int(round(y))
        cv2.line(overlay, (x0, yy), (x1, yy), color, 2)
        cv2.putText(
            overlay, label, (x0, max(14, yy - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA,
        )

    def _mark_roi(roi: RoiRect, y, color, label):
        x0, x1 = sorted((int(roi.x0), int(roi.x1)))
        y0, y1 = sorted((int(roi.y0), int(roi.y1)))
        x0, x1 = max(0, x0), min(cw - 1, x1)
        y0, y1 = max(0, y0), min(ch - 1, y1)
        cv2.rectangle(overlay, (x0, y0), (x1, y1), color, 2)
        yy = int(round(y))
        cv2.line(overlay, (x0, yy), (x1, yy), color, 2)
        cv2.putText(
            overlay, label, (x0, max(14, y0 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA,
        )

    if measure_mode == "roi":
        _mark_roi(req.a_roi, y_a, (0, 255, 0), f"A {h_a:.3f}mm")
        _mark_roi(req.b_roi, y_b, (0, 0, 255), f"B {h_b:.3f}mm")
    else:
        _mark_range(req.a_x0, req.a_x1, y_a, (0, 255, 0), f"A {h_a:.3f}mm")
        _mark_range(req.b_x0, req.b_x1, y_b, (0, 0, 255), f"B {h_b:.3f}mm")

    return {
        **_overlay_payload(overlay, lm.profile_to_points(profile)),
        "height_a_mm": round(h_a, 4),
        "height_b_mm": round(h_b, 4),
        "step_diff_mm": round(abs(h_a - h_b), 4),
        "y_a": round(y_a, 2),
        "y_b": round(y_b, 2),
        "measure_mode": measure_mode,
        "a_roi": req.a_roi.model_dump() if req.a_roi is not None else None,
        "b_roi": req.b_roi.model_dump() if req.b_roi is not None else None,
        "lut_file": os.path.basename(lut_path),
        "lut_y_range": lut_range,
        "lut_created_at": lut.get("created_at"),
        "image_size": {"width": int(cw), "height": int(ch)},
    }


# ─────────────────────────────────────────────────────────────
# 단계 D-0: 간격용 mm/px (체커보드 한 칸 = square_size_mm / square_px)
# ─────────────────────────────────────────────────────────────
@router.get("/gap/scale/{camera_id}")
async def get_gap_scale(camera_id: int):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})
    saved = lm.load_gap_scale(CALIB_DIR, camera_id)
    if not saved:
        return {"exists": False, "mm_per_px": None}
    return {"exists": True, **saved}


@router.post("/gap/scale/{camera_id}")
async def compute_gap_scale(camera_id: int, req: GapScaleRequest = GapScaleRequest()):
    """측정면과 같은 거리에 체커보드를 두고 mm/px = square_mm / 칸_px 를 계산·저장."""
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    undistorted, meta, err = await _capture_undistorted(camera_id, req.calibration_file)
    if err is not None:
        return err

    calib_file = meta.get("_calibration_file")
    pattern = meta.get("pattern_inner_corners") or [DEFAULT_INNER_COLS, DEFAULT_INNER_ROWS]
    try:
        default_cols = int(pattern[0])
        default_rows = int(pattern[1])
    except Exception:
        default_cols, default_rows = DEFAULT_INNER_COLS, DEFAULT_INNER_ROWS

    inner_cols = int(req.inner_cols or default_cols or DEFAULT_INNER_COLS)
    inner_rows = int(req.inner_rows or default_rows or DEFAULT_INNER_ROWS)
    square_mm = float(
        req.square_size_mm
        if req.square_size_mm is not None
        else (meta.get("square_size_mm") or DEFAULT_SQUARE_MM)
    )

    session = CalibrationSession(
        camera_id=camera_id,
        config=CalibrationConfig(
            inner_cols=inner_cols,
            inner_rows=inner_rows,
            square_size_mm=square_mm,
        ),
    )
    found, corners = session.detect_corners_for_capture(undistorted)
    if not found or corners is None:
        overlay = undistorted.copy()
        cv2.putText(
            overlay,
            "Checkerboard NOT found",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": (
                    "체커보드를 찾지 못했습니다. 측정면과 같은 거리에 보드를 두고, "
                    f"내부 코너 {inner_cols}×{inner_rows}, 칸 {square_mm}mm 설정을 확인하세요."
                ),
                "image": _b64_jpeg(overlay),
                "inner_cols": inner_cols,
                "inner_rows": inner_rows,
                "square_size_mm": square_mm,
            },
        )

    stats = lm.estimate_checker_square_px(corners, inner_cols, inner_rows)
    # 간격(가로)에는 가로 칸 길이를 우선 사용
    square_px_x = stats.get("square_px_x")
    square_px = square_px_x if square_px_x else stats.get("square_px")
    mm_per_px = lm.compute_mm_per_px_from_checker(square_mm, square_px)
    if mm_per_px is None:
        return JSONResponse(status_code=422, content={"error": "칸 픽셀 길이를 계산하지 못했습니다."})

    mm_per_px_x = lm.compute_mm_per_px_from_checker(square_mm, stats.get("square_px_x"))
    mm_per_px_y = lm.compute_mm_per_px_from_checker(square_mm, stats.get("square_px_y"))

    ch, cw = undistorted.shape[:2]
    overlay = undistorted.copy()
    cv2.drawChessboardCorners(overlay, (inner_cols, inner_rows), corners, True)
    # 대표 가로 칸 표시
    grid = corners.reshape(inner_rows, inner_cols, 2)
    mid_r = inner_rows // 2
    p0 = tuple(np.round(grid[mid_r, 0]).astype(int))
    p1 = tuple(np.round(grid[mid_r, 1]).astype(int))
    cv2.line(overlay, p0, p1, (0, 255, 0), 3)
    label = f"{square_mm}mm / {square_px:.2f}px = {mm_per_px:.6f} mm/px"
    cv2.putText(
        overlay, label, (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2, cv2.LINE_AA,
    )

    payload = {
        "mm_per_px": round(float(mm_per_px), 8),
        "mm_per_px_x": None if mm_per_px_x is None else round(float(mm_per_px_x), 8),
        "mm_per_px_y": None if mm_per_px_y is None else round(float(mm_per_px_y), 8),
        "square_px": round(float(square_px), 4),
        "square_px_x": None if stats.get("square_px_x") is None else round(float(stats["square_px_x"]), 4),
        "square_px_y": None if stats.get("square_px_y") is None else round(float(stats["square_px_y"]), 4),
        "square_size_mm": square_mm,
        "inner_cols": inner_cols,
        "inner_rows": inner_rows,
        "calibration_file": calib_file,
        "image_size": {"width": int(cw), "height": int(ch)},
        "formula": "mm_per_px = square_size_mm / square_px",
    }
    if req.save:
        if not calib_file:
            return JSONResponse(
                status_code=400,
                content={"error": "저장할 캘리브레이션 파일이 없습니다. 캘리브레이션을 먼저 선택·저장하세요."},
            )
        try:
            path = lm.attach_plane_scale_to_calibration(CALIB_DIR, calib_file, payload)
        except (ValueError, FileNotFoundError) as e:
            return JSONResponse(status_code=404, content={"error": str(e)})
        # 레거시 호환: gap_scale.json에도 미러 저장
        lm.save_gap_scale(CALIB_DIR, camera_id, {**payload, "calibration_file": calib_file})
        attached = lm.load_plane_scale_from_calibration(CALIB_DIR, calib_file) or {}
        payload["saved"] = True
        payload["attached_to"] = os.path.basename(path)
        payload["saved_at"] = attached.get("saved_at")
        payload["plane_scale"] = attached
    else:
        payload["saved"] = False

    payload["image"] = _b64_jpeg(overlay)
    return payload


# ─────────────────────────────────────────────────────────────
# 단계 D: 간격 측정 (레이저 직선 끝점 사이 거리)
# ─────────────────────────────────────────────────────────────
@router.post("/measure/gap/{camera_id}")
async def measure_gap(camera_id: int, req: GapMeasureRequest):
    if camera_id < 0 or camera_id >= 4:
        return JSONResponse(status_code=400, content={"error": "Invalid camera_id"})

    stored = _FRAMES.get(camera_id)
    if req.use_stored and stored is not None and stored.get("img") is not None:
        undistorted = stored["img"]
        calib_file = stored.get("calibration_file")
    else:
        undistorted, meta, err = await _capture_undistorted(camera_id, req.calibration_file)
        if err is not None:
            return err
        calib_file = meta.get("_calibration_file")

    laser_kw = _laser_kwargs(req)

    if req.redetect or stored is None or stored.get("profile") is None:
        profile, _mask = lm.detect_laser_profile_for_gap(undistorted, **laser_kw)
    else:
        # 저장된 profile이 단차용(bridge)이면 간격이 사라질 수 있어 기본은 재검출
        profile = stored["profile"]

    points = lm.profile_to_points(profile)
    ch, cw = undistorted.shape[:2]
    _FRAMES[camera_id] = {
        "img": undistorted,
        "profile": profile,
        "points": points,
        "laser_kwargs": laser_kw,
        "calibration_file": calib_file,
        "size": (cw, ch),
        "mode": "gap",
    }

    mm_per_px, scale_meta = _resolve_gap_mm_per_px(
        camera_id,
        req.mm_per_px,
        req.use_saved_scale,
        calibration_file=req.calibration_file or calib_file,
    )

    # 밝은 코어 끝점 판정용 밝기 맵 (검출과 동일 정의, 레이저 색에 맞춘 우세 채널)
    _b = undistorted[:, :, 0].astype(np.float64)
    _g = undistorted[:, :, 1].astype(np.float64)
    _r = undistorted[:, :, 2].astype(np.float64)
    _main = _r if laser_kw.get("laser_color") == "red" else _b
    gap_intensity = np.maximum(_main, 0.5 * (_b + _g + _r))

    use_roi = req.a_roi is not None and req.b_roi is not None
    if use_roi:
        gap, err = lm.measure_gap_from_rois(
            profile,
            req.a_roi.model_dump(),
            req.b_roi.model_dump(),
            fit_len=req.fit_len,
            mm_per_px=mm_per_px,
            intensity=gap_intensity,
        )
    else:
        gap, err = lm.measure_gap_from_profile(
            profile,
            min_segment_px=req.min_segment_px,
            max_nan_bridge=req.max_nan_bridge,
            fit_len=req.fit_len,
            min_gap_px=req.min_gap_px,
            max_gap_px=req.max_gap_px,
            mm_per_px=mm_per_px,
            search_x0=req.search_x0,
            search_x1=req.search_x1,
            min_step_dy_px=req.min_step_dy_px,
            intensity=gap_intensity,
        )
    if err:
        overlay = lm.draw_profile(undistorted, profile)
        if use_roi:
            # ROI는 그렸는데 실패했을 때도 위치를 보여 줌
            try:
                for roi, color in (
                    (req.a_roi.model_dump(), (0, 255, 0)),
                    (req.b_roi.model_dump(), (0, 0, 255)),
                ):
                    x0, x1 = sorted((int(roi["x0"]), int(roi["x1"])))
                    y0, y1 = sorted((int(roi["y0"]), int(roi["y1"])))
                    cv2.rectangle(overlay, (x0, y0), (x1, y1), color, 2)
            except Exception:
                pass
        images = _overlay_payload(overlay, points)
        return JSONResponse(
            status_code=422,
            content={
                "error": err,
                "mode": "roi" if use_roi else "auto",
                **images,
                "valid_columns": len(points),
                "image_size": {"width": int(cw), "height": int(ch)},
            },
        )

    overlay = lm.draw_gap_overlay(undistorted, profile, gap)
    return {
        **_overlay_payload(overlay, points),
        "gap_px": gap["gap_px"],
        "gap_euclid_px": gap["gap_euclid_px"],
        "gap_mm": gap["gap_mm"],
        "gap_euclid_mm": gap["gap_euclid_mm"],
        "gap_bright_px": gap.get("gap_bright_px"),
        "gap_bright_mm": gap.get("gap_bright_mm"),
        "mm_per_px": gap["mm_per_px"],
        "step_dy_px": gap.get("step_dy_px"),
        "scale": scale_meta,
        "mode": gap.get("mode") or ("roi" if use_roi else "auto"),
        "left_end": gap["left_end"],
        "right_end": gap["right_end"],
        "left_end_bright": gap.get("left_end_bright"),
        "right_end_bright": gap.get("right_end_bright"),
        "left_segment": gap["left_segment"],
        "right_segment": gap["right_segment"],
        "segment_count": gap["segment_count"],
        "segments": gap["segments"],
        "candidate_count": gap["candidate_count"],
        "a_roi": gap.get("a_roi"),
        "b_roi": gap.get("b_roi"),
        "valid_columns": len(points),
        "calibration_file": calib_file,
        "image_size": {"width": int(cw), "height": int(ch)},
    }
