import io
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from routers.auth import role_required
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Data Ingestion Pipeline"])


@router.post("/upload")
async def upload_weekly_ledger(
        store_id: int = Form(...),
        file: UploadFile = File(...),
        user=role_required("ops", "manager")
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")

    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))

        raise HTTPException(
            status_code=501,
            detail="Upload received but integrity engine is not yet implemented."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error for store {store_id}: {e}")
        raise HTTPException(status_code=500, detail="File processing failed.")