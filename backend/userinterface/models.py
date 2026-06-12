from sqlalchemy import Column, Integer, Numeric, VARCHAR
from database import Base


class CameraFeature(Base):
    __tablename__ = "CAMERA_FEATURE"

    ID = Column(Integer, primary_key=True, index=True, autoincrement=True)
    CAMERA = Column(Integer)
    WIDTH = Column(Integer, nullable=True)
    HEIGHT = Column(Integer, nullable=True)
    EXPOSURE_TIME = Column(Numeric, nullable=True)
    GAIN_AUTO = Column(Integer, nullable=True)
    GAIN_dB = Column(Numeric, nullable=True)
    FPS_ENABLE = Column(Integer, nullable=True)
    FPS = Column(Numeric, nullable=True)
    PIXEL_FORMAT = Column(Integer, nullable=True)
    IP = Column(VARCHAR(255), nullable=True)
