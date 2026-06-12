import os
import sys
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)

import asyncio
import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime
from utils.camera_grab_v2 import (
    get_feature, set_feature, get_camera_status, get_device_list,
    start_grabbing, stop_grabbing, get_frame, get_frame_save, save_image, cameragrab,
    get_last_saved_path,
)
from schemas import CameraFeatureRequest

router = APIRouter(
    prefix="/camera",
    tags=["camera"]
)
@router.post("/start")
async def start_camera():
    try:
        await start_grabbing()
        return {"message": f"Camera started successfully"}
    except Exception as e:
        return {"error": f"Failed to start camera: {str(e)}"}
    
@router.post("/stop/")
async def stop_camera():
    try:
        await stop_grabbing()
        return {"message": f"Camera stopped successfully"}
    except Exception as e:
        return {"error": f"Failed to stop camera : {str(e)}"}

@router.post("/restart")
async def restart_camera():
    """카메라 재초기화 엔드포인트 (매핑 변경 후 사용)"""
    try:
        success = await cameragrab.restart()
        if success:
            return JSONResponse(
                status_code=200,
                content={"message": "Camera restarted successfully with new mapping"}
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to restart camera"}
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to restart camera: {str(e)}"}
        )

@router.post("/set_feature/{camera_id}")
async def set_camera_feature(
    camera_id: int,
    request: CameraFeatureRequest
):
    try:
        result = await set_feature(
            camera_id,
            request.feature.fpsenable,
            request.feature.fps,
            request.feature.gainauto,
            request.feature.gain,
            request.feature.exposuretime,
            request.feature.width,
            request.feature.height,
            request.feature.pixel_format
        )
        if result is None:
            return JSONResponse(
                status_code=400,
                content={"error": f"Failed to set camera {camera_id} features"}
            )
        return JSONResponse(
            status_code=200,
            content={"message": f"Camera {camera_id} features set successfully"}
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to set camera {camera_id} features: {str(e)}"}
        )
        
@router.post("/get_feature/{camera_id}")
async def get_camera_feature(camera_id: int):
    try:
        feature = await get_feature(camera_id)

        if feature is None:
            status = await get_camera_status(camera_id)
            all_status = await get_camera_status()
            ui_id = camera_id + 1
            detail = "device not open"
            if isinstance(status, dict):
                if not status.get("has_camera"):
                    db_ip = status.get("db_ip")
                    detail = "camera not mapped or not initialized"
                    if db_ip:
                        detail += f" (UI Camera {ui_id} DB IP: {db_ip})"
                elif not status.get("is_open"):
                    detail = "device not open (another app may be using the camera)"
            active_ui_ids = []
            active_slots = []
            if isinstance(all_status, dict):
                for cam in all_status.get("cameras", []):
                    if cam.get("has_camera"):
                        ui_cam = cam.get("ui_camera_id", cam["camera_id"] + 1)
                        active_ui_ids.append(ui_cam)
                        active_slots.append(
                            f"UI Camera {ui_cam}"
                            + (f" (IP: {cam['device_ip']})" if cam.get("device_ip") else "")
                        )
            if (
                active_slots
                and ui_id not in active_ui_ids
                and not (isinstance(status, dict) and status.get("has_camera"))
            ):
                detail += f". Actually connected: {', '.join(active_slots)}"
            return JSONResponse(
                status_code=404,
                content={"error": f"Failed to get UI Camera {ui_id} (slot {camera_id}) features: {detail}"}
            )

        return JSONResponse(
            status_code=200,
            content={"camera_id": camera_id, "feature": feature}
        )
    except Exception as e:
        print(f"Error getting features: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get camera {camera_id} features: {str(e)}"}
        )

@router.get("/last_saved_path")
async def get_last_saved_path_endpoint(camera_id: int = 1):
    """
    카메라별 마지막 저장된 이미지 경로(f0000) 반환.
    camera_id: 1-4 (UI 기준)
    """
    try:
        path = get_last_saved_path(camera_id)
        return {"camera_id": camera_id, "image_path": path}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/last_saved_paths")
async def get_all_last_saved_paths_endpoint():
    """
    카메라 1~4 전체의 마지막 저장된 이미지 경로(f0000) 반환.
    """
    try:
        result = {}
        for cam_id in range(1, 5):
            path = get_last_saved_path(cam_id)
            result[str(cam_id)] = path
        return result
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.post("/save/{camera_id}")
async def save_camera_image(camera_id: int):
    try:
        # frame 파라미터는 기본값으로 설정 (추후 요청 본문에서 받을 수 있도록 수정 가능)
        result = await save_image(camera_id, "D:oneclick/stream", 1)
        if result:
            return {"message": f"Camera {camera_id} saved successfully"}
        else:
            return {"error": f"Failed to save camera {camera_id}"}
    except Exception as e:
        print(f"Save error: {str(e)}")
        return {"error": f"Failed to save camera {camera_id}: {str(e)}"}
    
@router.websocket("/ws/{camera_id}")
async def websocket_endpoint(websocket: WebSocket, camera_id: int):
    await websocket.accept()
    try:
        # 카메라 ID 유효성 확인
        if camera_id < 0 or camera_id >= 4:
            print(f"Invalid camera_id: {camera_id}")
            await websocket.close(code=1000, reason="Invalid camera ID")
            return
        
        # 웹소켓 연결 시 카메라 상태 확인
        status = await get_camera_status(camera_id)
        if not status:
            print(f"Camera {camera_id} status not available")
            await websocket.close(code=1000, reason="Camera status not available")
            return
        if not status.get("is_running", False):
            print(f"Camera {camera_id} is not running")
            await websocket.close(code=1000, reason="Camera is not running")
            return
        if not status.get("has_camera", False):
            print(f"Camera {camera_id} not initialized")
            await websocket.close(code=1000, reason="Camera not initialized")
            return

        # 프레임이 준비될 때까지 초기 대기 (타임아웃 단축)
        frame_ready = False
        for _ in range(5):  # 최대 2.5초 대기 (0.5초 * 5)
            try:
                frame = await asyncio.wait_for(get_frame(camera_id, stream_width=1280, stream_height=720), timeout=0.3)
                if frame is not None:
                    frame_ready = True
                    break
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass
            await asyncio.sleep(0.5)

        # 프레임 전송 루프
        consecutive_failures = 0
        max_failures = 10
        
        # 첫 프레임 전송 전 약간의 대기 (클라이언트가 준비될 시간 확보)
        await asyncio.sleep(0.3)
        
        while True:
            # WebSocket이 여전히 연결되어 있는지 확인
            try:
                if websocket.client_state.name != 'CONNECTED':
                    print(f"WebSocket for camera {camera_id} is not connected, breaking loop")
                    break
            except Exception:
                # client_state 확인 중 에러 발생 시 연결이 끊긴 것으로 간주
                break
            
            try:
                # 타임아웃을 설정하여 프레임 가져오기 (최대 0.5초로 증가)
                # 저장 중일 때는 None이 반환되므로 프레임 전송을 건너뜀
                frame = await asyncio.wait_for(get_frame(camera_id, stream_width=1280, stream_height=720), timeout=0.5)
                
                if frame is not None:
                    try:
                        # frame은 bytes 객체이므로 그대로 사용
                        frame_bytes = frame if isinstance(frame, bytes) else (frame.tobytes() if hasattr(frame, 'tobytes') else None)
                        if frame_bytes and len(frame_bytes) > 0:
                            # WebSocket 상태를 다시 확인한 후 전송
                            try:
                                if websocket.client_state.name == 'CONNECTED':
                                    await websocket.send_bytes(frame_bytes)
                                    consecutive_failures = 0  # 성공 시 실패 카운터 리셋
                                else:
                                    print(f"WebSocket for camera {camera_id} disconnected before send")
                                    break
                            except WebSocketDisconnect:
                                # 클라이언트가 연결을 끊었을 때
                                print(f"Client disconnected from camera {camera_id} during frame send")
                                break
                            except Exception as send_error:
                                # 이미 닫힌 WebSocket에 보내려고 할 때
                                consecutive_failures += 1
                                if consecutive_failures >= max_failures:
                                    error_type = type(send_error).__name__
                                    error_msg = str(send_error) if send_error else "Unknown error"
                                    print(f"Error sending frame to camera {camera_id} ({consecutive_failures} failures): [{error_type}] {error_msg}")
                                    break
                    except Exception as frame_error:
                        # 프레임 처리 에러
                        consecutive_failures += 1
                        if consecutive_failures >= max_failures:
                            print(f"Camera {camera_id}: Frame processing error ({consecutive_failures} failures): {frame_error}")
                            break
                else:
                    # 프레임이 None인 경우 (저장 중이거나 버퍼 없음)
                    # 저장 중일 때는 실패로 카운트하지 않고 짧은 대기 후 재시도
                    # 연속 실패가 너무 많을 때만 중단
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures * 2:  # 저장 중일 수 있으므로 여유를 둠
                        print(f"Camera {camera_id}: Too many consecutive frame failures ({consecutive_failures}), breaking")
                        break
                    # 저장 중일 가능성이 있으므로 짧은 대기
                    await asyncio.sleep(0.1)
            except asyncio.TimeoutError:
                # 프레임 가져오기 타임아웃
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    print(f"Camera {camera_id}: Frame timeout exceeded ({consecutive_failures} failures)")
                    break
            except WebSocketDisconnect:
                # 프레임 가져오는 중 연결이 끊겼을 때
                print(f"Client disconnected from camera {camera_id} during frame get")
                break
            except Exception as frame_error:
                # 프레임 가져오기 에러
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    print(f"Camera {camera_id}: Frame error ({consecutive_failures} failures): {frame_error}")
                    break
                
            # 프레임 전송 간격 조정 (여러 카메라 동시 스트리밍 시 부하 분산)
            await asyncio.sleep(0.2)  # 안정적인 전송을 위해 0.2초로 설정
    except WebSocketDisconnect:
        print(f"Client disconnected from camera {camera_id}")
    except Exception as e:
        print(f"WebSocket error for camera {camera_id}: {e}")
    finally:
        try:
            # WebSocket이 아직 연결되어 있을 때만 닫기
            if websocket.client_state.name == 'CONNECTED':
                await websocket.close(code=1000)
        except Exception as e:
            # 이미 닫힌 WebSocket에 대해 에러 무시
            pass

@router.get("/status")
async def get_status(camera_id: int = None):
    """카메라 상태 확인 엔드포인트 (camera_id 쿼리 파라미터가 없으면 모든 카메라 상태 반환)
    
    사용 예시:
    - GET /camera/status : 모든 카메라 상태 반환
    - GET /camera/status?camera_id=0 : 카메라 0번 상태 반환
    """
    try:
        status = await get_camera_status(camera_id)
        if status is None:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get camera status" + (f" for camera {camera_id}" if camera_id is not None else "")}
            )
        return JSONResponse(
            status_code=200,
            content={"status": status}
        )
    except Exception as e:
        print(f"Error getting camera status: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get camera status: {str(e)}"}
        )

@router.get("/devices")
async def get_devices():
    """연결된 디바이스 리스트 조회 엔드포인트"""
    try:
        devices = await get_device_list()
        if devices is None:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to get device list"}
            )
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "device_count": len(devices),
                "devices": devices
            }
        )
    except Exception as e:
        print(f"Error getting device list: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get device list: {str(e)}"}
        )
