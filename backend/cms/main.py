# -*- coding: utf-8 -*-
"""EZVision CMS 서버 — 캘리브레이션 / LUT / 측정 / 레이저 3D.

플랫폼의 한 기능(별도 서버). 카메라 제어는 camera 서버(7070)가 담당하고,
CMS는 필요한 원본 프레임을 `utils.camera_client` 로 HTTP 요청해서 가져온다.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import laserplane

app = FastAPI(title="EZVision CMS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:7070",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(laserplane.router)


@app.get("/")
async def root():
    return {
        "message": "EZVision CMS server (calibration / LUT / measurement / laser 3D)",
        "status": "connected",
        "camera_url": os.environ.get("CAMERA_URL", "http://localhost:7070"),
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=7060, reload=False, workers=1)
