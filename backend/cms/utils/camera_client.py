# -*- coding: utf-8 -*-
"""CMS 서버가 camera 서버(7070)에서 프레임을 HTTP로 가져오는 클라이언트.

플랫폼 구조상 camera와 cms는 별도 서버(프로세스)라, cms는 카메라 SDK에 직접
접근하지 않고 camera 서버의 `/camera/frame/{id}` 로 원본 프레임을 요청한다.
기존 `utils.camera_grab_v2.get_frame_bgr` 와 시그니처가 호환된다.
"""
import os
from typing import Optional

import cv2
import httpx
import numpy as np

CAMERA_URL = os.environ.get("CAMERA_URL", "http://localhost:7070")

# 기존 camera_grab_v2 와 동일한 표시 해상도 상수 (calibration 프리뷰용)
STREAM_DISPLAY_WIDTH = 1280
STREAM_DISPLAY_HEIGHT = 720


def letterbox_bgr(bgr: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """비율 유지 + 레터박스로 target 크기에 맞춤 (camera_grab_v2 와 동일)."""
    h, w = bgr.shape[:2]
    scale = min(target_w / w, target_h / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    if new_w == target_w and new_h == target_h:
        return resized
    canvas = np.zeros((target_h, target_w, 3), dtype=bgr.dtype)
    x0 = (target_w - new_w) // 2
    y0 = (target_h - new_h) // 2
    canvas[y0 : y0 + new_h, x0 : x0 + new_w] = resized
    return canvas


async def get_frame_bgr(camera_id: int) -> Optional[np.ndarray]:
    """camera 서버에서 원본 해상도 BGR 프레임 1장을 받아온다 (없으면 None)."""
    url = f"{CAMERA_URL}/camera/frame/{int(camera_id)}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
        if resp.status_code != 200 or not resp.content:
            return None
        arr = np.frombuffer(resp.content, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None
