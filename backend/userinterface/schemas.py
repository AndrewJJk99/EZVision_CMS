from typing import Optional
from pydantic import BaseModel, Field


class CameraFeatureBase(BaseModel):
    CAMERA: Optional[int] = None
    WIDTH: Optional[int] = None
    HEIGHT: Optional[int] = None
    EXPOSURE_TIME: Optional[float] = None
    GAIN_AUTO: Optional[int] = None
    GAIN_dB: Optional[float] = None
    FPS_ENABLE: Optional[int] = None
    FPS: Optional[float] = None
    PIXEL_FORMAT: Optional[int] = None
    IP: Optional[str] = Field(None, max_length=255)


class CameraFeatureCreate(CameraFeatureBase):
    pass


class CameraFeatureResponse(CameraFeatureBase):
    ID: int

    class Config:
        from_attributes = True
