"""EZVision_color 호환용 no-op 엔드포인트 — CMS에서는 sensor/trigger/colorlens 미사용."""

from fastapi import APIRouter

router = APIRouter(tags=["legacy-stubs"])


@router.get("/camera/latest_shutter")
def latest_shutter_stub():
    return [{"STATUS": "E"}]


@router.get("/camera/get_camera_light")
def get_camera_light_stub():
    return []


@router.get("/colorlens/trigger/policy")
def colorlens_trigger_policy_stub():
    return {}


@router.get("/colorlens/settings/body")
def colorlens_settings_body_stub():
    return {}


@router.get("/colorlens/trigger/color_sensor/{sensor_id}")
def colorlens_color_sensor_stub(sensor_id: int):
    return {"sensor_id": sensor_id, "enabled": False}


@router.get("/colorlens/rest/iolink/{port}")
def colorlens_iolink_stub(port: int):
    return {"port": port, "connected": False}
