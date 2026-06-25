from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import Request
from fastapi.responses import Response
import os
import uvicorn

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(BASE_DIR, "build")
INDEX_PATH = os.path.join(BUILD_DIR, "index.html")
STATIC_DIR = os.path.join(BUILD_DIR, "static")

# React 정적 리소스 (JS, CSS 등) - 가장 먼저 mount해야 함
if os.path.exists(STATIC_DIR):
    app.mount(
        "/static",
        StaticFiles(directory=STATIC_DIR),
        name="static"
    )


@app.get("/favicon.ico")
async def favicon():
    favicon_path = os.path.join(BUILD_DIR, "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return Response(status_code=404)


@app.get("/manifest.json")
async def manifest():
    manifest_path = os.path.join(BUILD_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        return FileResponse(manifest_path, media_type="application/json")
    return Response(status_code=404)


@app.get("/robots.txt")
async def robots():
    robots_path = os.path.join(BUILD_DIR, "robots.txt")
    if os.path.exists(robots_path):
        return FileResponse(robots_path, media_type="text/plain")
    return Response(status_code=404)


@app.get("/")
async def root():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    return Response(content="index.html not found. Please build the React app first.", status_code=404)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "build_dir_exists": os.path.exists(BUILD_DIR),
        "index_exists": os.path.exists(INDEX_PATH),
        "static_exists": os.path.exists(STATIC_DIR)
    }


@app.get("/{full_path:path}")
async def react_app(request: Request, full_path: str):
    if full_path.startswith("static/"):
        return Response(status_code=404)

    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    return Response(content="index.html not found. Please build the React app first.", status_code=404)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3000,
        reload=True,
        reload_excludes=["*/__pycache__/*", "*.pyc"],
    )
