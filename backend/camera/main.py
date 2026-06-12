from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from routers import camera, calibration
from utils.camera_grab_v2 import cameragrab
from datetime import datetime
import uvicorn
import asyncio
import os

CAMERA_INIT_RETRY_DELAY_SEC = 2.0
CAMERA_STARTUP_WAIT_SEC = 1.5


async def _start_cameras_with_retry():
    """이전 프로세스가 카메라 핸들을 놓을 시간을 준 뒤 초기화"""
    await cameragrab.cleanup()
    await asyncio.sleep(CAMERA_STARTUP_WAIT_SEC)
    return await cameragrab.start_grabbing()


@asynccontextmanager
async def lifespan(app: FastAPI):
    retry_task = None
    try:
        success = await _start_cameras_with_retry()
        if not success:
            print("Failed to initialize camera on startup, scheduling background retry...")

            async def background_retry():
                for attempt in range(10):
                    await asyncio.sleep(CAMERA_INIT_RETRY_DELAY_SEC)
                    if cameragrab.is_initialized:
                        return
                    print(f"Background camera init retry {attempt + 1}/10...")
                    if await _start_cameras_with_retry():
                        print("Background camera init succeeded")
                        return
                print("Background camera init gave up after 10 attempts")

            retry_task = asyncio.create_task(background_retry())
        yield
    except asyncio.CancelledError:
        print("Server shutdown initiated...")
        raise
    except Exception as e:
        print(f"Error during camera lifecycle: {str(e)}")
        yield
    finally:
        if retry_task is not None:
            retry_task.cancel()
            try:
                await retry_task
            except asyncio.CancelledError:
                pass
        try:
            print("Shutting down server...")
            await asyncio.wait_for(cameragrab.cleanup(), timeout=8.0)
            print("Camera cleaned up successfully")
        except asyncio.TimeoutError:
            print("Warning: Camera cleanup timed out, forcing shutdown")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error cleaning up camera during shutdown: {e}")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:7000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"], 
)

app.include_router(camera.router)
app.include_router(calibration.router)

@app.get("/")
async def root():
    response = {
        "message": "EZVision CMS Camera server",
        "status": "connected",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
    }          
    return response

if __name__ == "__main__":
    # 카메라 SDK는 hot-reload 시 Access Denied가 자주 발생하므로 기본 비활성화
    enable_reload = os.getenv("CAMERA_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=7070, 
        reload=enable_reload,
        reload_excludes=["*/__pycache__/*", "*.pyc"],
        workers=1
        )
