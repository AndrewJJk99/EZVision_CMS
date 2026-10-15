from datetime import datetime
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import camera, legacy_stubs

app = FastAPI(title="EZVision CMS UI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:13000",
        "http://127.0.0.1:13000",
        "http://localhost:17070",
        "http://localhost:18000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(camera.router)
app.include_router(legacy_stubs.router)


@app.on_event("startup")
async def startup_event():
    init_db()
    print("EZVision CMS UI API ready (camera IP mapping)")


@app.get("/")
async def root():
    return {
        "message": "EZVision CMS UI server",
        "status": "connected",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("UI_API_PORT", "18000")),
        reload=False,
        workers=1,
    )
