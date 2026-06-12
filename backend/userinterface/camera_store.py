import logging
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from models import CameraFeature
from schemas import CameraFeatureCreate

logger = logging.getLogger(__name__)


def read_camera_features(skip: int = 0, limit: int = 4, db: Session = None):
    try:
        return db.query(CameraFeature).offset(skip).limit(limit).all()
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise


def save_camera_feature(camera_feature: CameraFeatureCreate, db: Session):
    try:
        existing = db.query(CameraFeature).filter(
            CameraFeature.CAMERA == camera_feature.CAMERA
        ).first()

        if existing:
            for key, value in camera_feature.model_dump(exclude_unset=True).items():
                setattr(existing, key, value)
            db.commit()
            db.refresh(existing)
            return existing

        row = CameraFeature(**camera_feature.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("Database error while saving camera feature: %s", e)
        raise
