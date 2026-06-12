from pydantic import BaseModel


class CameraFeatureData(BaseModel):
    fpsenable: int
    fps: float
    gainauto: int
    gain: float
    exposuretime: float
    width: int
    height: int
    pixel_format: int


class CameraFeatureRequest(BaseModel):
    feature: CameraFeatureData
