import io
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from database import supabase
from routers.auth import get_current_user # Explicit path

router = APIRouter(prefix="/api", tags=["Data Ingestion Pipeline"])

@router.post("/upload")
async def upload_weekly_ledger(
        store_id: int = Form(...),
        file: UploadFile = File(...),
        user=Depends(get_current_user)
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV allowed.")

    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        return {"success": True, "message": f"Pipeline executed for {user.email}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")