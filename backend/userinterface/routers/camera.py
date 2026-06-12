from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from schemas import CameraFeatureCreate, CameraFeatureResponse
from camera_store import read_camera_features, save_camera_feature

router = APIRouter(prefix="/camera", tags=["camera"])


@router.get("/get_feature", response_model=list[CameraFeatureResponse])
def read_camera_features_endpoint(skip: int = 0, limit: int = 4, db: Session = Depends(get_db)):
    try:
        return read_camera_features(skip, limit, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save_feature", response_model=CameraFeatureResponse)
async def save_camera_feature_endpoint(
    camera_feature: CameraFeatureCreate,
    db: Session = Depends(get_db),
):
    try:
        return save_camera_feature(camera_feature, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
