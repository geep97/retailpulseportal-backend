from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from database import supabase, admin_supabase

router = APIRouter(tags=["Authentication"])
security = HTTPBearer()

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
async def login(credentials: LoginRequest):
    try:
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        return {"access_token": response.session.access_token, "token_type": "bearer"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")

@router.post("/admin/create-user")
async def create_user(user_data: LoginRequest):
    try:
        # Using admin_supabase to bypass email confirmation
        response = admin_supabase.auth.admin.create_user({
            "email": user_data.email,
            "password": user_data.password,
            "email_confirm": True
        })
        return {"message": "User created successfully", "user": response.user}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_response.user
    except Exception:
        raise HTTPException(status_code=401, detail="Could not validate credentials")